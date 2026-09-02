"""The long-lived `/api/stream` connection: connect, catch up, reconnect on any disconnect.

Follows the relay's own reconnect contract (`lios_relay.api.stream` module docstring)
verbatim: remember "now" before connecting, catch up via `GET /api/items?since=` after every
successful connect (including the first), and reconnect with `relaylink.backoff`'s schedule on
any disconnect -- server-initiated or not, never a reason to stop trying.

🚨 Unverified against a live relay or a real `Soup.Session`: `websocket_connect_async`'s exact
PyGObject argument order (message, origin, protocols, io_priority, cancellable, callback) is
written from the libsoup3 C API and could not be exercised here -- there is no relay running
and no network access from `pai-vm` into one. Confirm against a real connection before
shipping.

Untestable in this environment without a running relay to connect to.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
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
    it was discovered.
    """

    def __init__(
        self,
        *,
        relay_url: str,
        device_token: str,
        session: Soup.Session,
        on_item: Callable[[ItemSummary], None],
    ) -> None:
        self._relay_url = relay_url
        self._device_token = device_token
        self._session = session
        self._on_item = on_item
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
        connect_time = datetime.now(UTC)
        message = Soup.Message.new("GET", endpoints.stream_url(self._relay_url))
        message.get_request_headers().append(
            "Authorization", endpoints.auth_header(self._device_token)["Authorization"]
        )
        self._session.websocket_connect_async(
            message,
            None,
            [],
            GLib.PRIORITY_DEFAULT,
            None,
            lambda session, result: self._on_connected(session, result, connect_time),
        )

    def _on_connected(
        self, session: Soup.Session, result: Any, connect_time: datetime
    ) -> None:
        try:
            self._connection = session.websocket_connect_finish(result)
        except GLib.Error as exc:
            logger.warning("relay stream connect failed: %s", exc)
            self._schedule_reconnect()
            return
        self._attempt = 0
        self._connection.connect("message", self._on_message)
        self._connection.connect("closed", lambda *_args: self._on_closed())
        self._catch_up(connect_time)

    def _catch_up(self, since: datetime) -> None:
        """Pull everything created since `since` -- covers the gap since the last disconnect."""
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
        for item in items:
            self._on_item(item)

    def _on_message(
        self,
        connection: Soup.WebsocketConnection,
        message_type: Soup.WebsocketDataType,
        message: Any,
    ) -> None:
        if message_type != Soup.WebsocketDataType.TEXT:
            return
        payload = bytes(message).decode("utf-8")
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
