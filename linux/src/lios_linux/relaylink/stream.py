"""The long-lived `/api/stream` connection: connect, catch up, reconnect on any disconnect.

Every catch-up -- the first connect this process ever makes, and every reconnect after it --
resumes from `get_catch_up_since()`'s current answer rather than a timestamp captured at
connect time. Capturing "now" right before connecting is wrong twice over: it misses whatever
arrived during the disconnected gap itself (the gap ends before the reconnect fires, not
after), and it does not survive the process restarting at all, since nothing remembers where
the previous run left off. `get_catch_up_since` is a callback rather than a value so the
caller (`app.py`) can own where that watermark actually lives and how it advances; this module
only ever asks for the current answer, right when it is about to use it.

Reconnects with `relaylink.backoff`'s schedule on any disconnect -- server-initiated or not,
never a reason to stop trying.

`_catch_up` runs its REST call on a worker thread and hops back to the main loop via
`GLib.idle_add` before calling `on_item`, matching `app.py`'s own rule that only the main loop
may touch GTK/history state -- `_on_connected` (and so `_catch_up`) fires on the GTK main loop,
and `rest.list_items_since` blocks the calling thread until the response arrives.

🚨 Unverified against a live relay or a real `Soup.Session`: `websocket_connect_async`'s exact
PyGObject argument order (message, origin, protocols, io_priority, cancellable, callback) is
written from the libsoup3 C API and could not be exercised in this headless environment, with
no relay running and no network access into one. Confirm against a real connection before
shipping.

Untestable end to end in this environment without a running relay to connect to. `_on_message`
itself is an exception -- it needs only a real `GLib.Bytes` and `Soup.WebsocketDataType`, no
socket at all, and is unit-tested directly against those; likewise `_catch_up`, driven by a
fake `Soup.Session`-shaped object rather than a real connection and a couple of iterations of
the real `GLib.MainContext` to let its worker thread's `idle_add` land.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

import gi

gi.require_version("Soup", "3.0")
gi.require_version("GLib", "2.0")

from gi.repository import GLib, Soup  # noqa: E402
from lios_protocol.wire import ItemSummary, StreamEvent  # noqa: E402

from lios_linux.relaylink import endpoints, rest  # noqa: E402
from lios_linux.relaylink.backoff import next_delay  # noqa: E402

logger = logging.getLogger(__name__)


class StreamConnection:
    """Owns the WebSocket, the reconnect loop, and the catch-up call after each connect.

    `on_item` is called once per item, whether it was announced live over the socket or
    learned about from the catch-up list -- one place to handle a new item regardless of how
    it was discovered. The caller is expected to treat an already-known item id as a safe
    no-op, since the two routes can genuinely overlap: a catch-up spanning the moment the
    socket opens can list an item the live stream is about to announce anyway.
    """

    def __init__(
        self,
        *,
        relay_url: str,
        device_token: str,
        session: Soup.Session,
        on_item: Callable[[ItemSummary], None],
        get_catch_up_since: Callable[[], datetime],
    ) -> None:
        self._relay_url = relay_url
        self._device_token = device_token
        self._session = session
        self._on_item = on_item
        self._get_catch_up_since = get_catch_up_since
        self._attempt = 0
        self._stopped = True
        self._connection: Soup.WebsocketConnection | None = None

    def start(self) -> None:
        """Connect, and keep reconnecting on every disconnect until :meth:`stop`."""
        self._stopped = False
        self._connect()

    def stop(self) -> None:
        """Close the connection and stop reconnecting."""
        self._stopped = True
        if self._connection is not None:
            self._connection.close(Soup.WebsocketCloseCode.NORMAL, None)
            self._connection = None

    def _connect(self) -> None:
        if self._stopped:
            return
        message = Soup.Message.new("GET", endpoints.stream_url(self._relay_url))
        if message is None:
            logger.warning("relay stream: malformed URL %s", self._relay_url)
            self._schedule_reconnect()
            return
        message.get_request_headers().append(
            "Authorization", endpoints.auth_header(self._device_token)["Authorization"]
        )
        self._session.websocket_connect_async(
            message, None, [], GLib.PRIORITY_DEFAULT, None, self._on_connected
        )

    def _on_connected(self, session: Soup.Session, result: Any) -> None:
        try:
            self._connection = session.websocket_connect_finish(result)
        except GLib.Error as exc:
            logger.warning("relay stream connect failed: %s", exc)
            self._schedule_reconnect()
            return
        self._attempt = 0
        self._connection.connect("message", self._on_message)
        self._connection.connect("closed", lambda *_args: self._on_closed())
        self._catch_up()

    def _catch_up(self) -> None:
        """Pull everything created since the current watermark -- whatever was missed,
        however long the gap was or however it came about.

        The watermark itself is read here, on the caller's thread (the GTK main loop), since
        `get_catch_up_since` reaches into history state; the REST call that follows is the
        slow part and runs on a worker thread instead, so a connect or reconnect never leaves
        the main loop blocked on the network.
        """
        since = self._get_catch_up_since()

        def worker() -> None:
            try:
                items = rest.list_items_since(
                    self._session,
                    relay_url=self._relay_url,
                    device_token=self._device_token,
                    since=since,
                )
            except rest.RelayError as exc:
                logger.warning("relay catch-up list failed: %s", exc)
                return
            GLib.idle_add(self._deliver_catch_up_items, items)

        threading.Thread(target=worker, daemon=True).start()

    def _deliver_catch_up_items(self, items: list[ItemSummary]) -> bool:
        for item in items:
            self._on_item(item)
        return bool(GLib.SOURCE_REMOVE)

    def _on_message(
        self,
        connection: Soup.WebsocketConnection,
        message_type: Soup.WebsocketDataType,
        message: Any,
    ) -> None:
        if message_type != Soup.WebsocketDataType.TEXT:
            return
        payload = message.get_data().decode("utf-8")
        if '"type":"ping"' in payload:
            return
        event = StreamEvent.model_validate_json(payload)
        self._on_item(event.item)

    def _on_closed(self) -> None:
        self._connection = None
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._stopped:
            return
        delay = next_delay(self._attempt)
        self._attempt += 1
        GLib.timeout_add_seconds(max(int(delay), 1), self._reconnect_tick)

    def _reconnect_tick(self) -> bool:
        self._connect()
        return bool(GLib.SOURCE_REMOVE)
