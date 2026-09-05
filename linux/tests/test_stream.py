"""`StreamConnection._on_message` decodes a real `GLib.Bytes`, not `bytes(message)`.

`bytes(some_glib_bytes)` raises `TypeError: cannot convert 'Bytes' object to bytes` -- the
message signal's payload never converts that way, only `.get_data()` does, matching every
other call site in this tree. This is why nothing the phone sent ever reached the laptop, and
why the failure repeated on every keepalive too, since the ping check ran after the broken
conversion.

Also covers `_catch_up`: it must ask its `get_catch_up_since` callback for "since" at the
moment it runs, not use a value captured earlier, it must dispatch every item the list returns
-- the watermark itself never regressing is `HistoryStore`'s own job and is tested in
`tests/test_history_watermark.py` -- and it must never block the caller on the REST call
itself, since that caller is the GTK main loop.

Also covers the staleness watchdog, which is what notices a connection that died without
saying so -- an IPv6 privacy address rotating away underneath the socket, a NAT table
forgetting the flow, a suspend. The kernel keeps reporting such a connection as ESTABLISHED
and libsoup never emits `closed`, so silence past `STALE_AFTER_SECONDS` is the only evidence
there is; a client that waits for a close frame instead waits forever. The generation guard is
tested alongside it, since a late `closed` signal for a socket the watchdog already gave up on
would otherwise open a second connection in parallel with the replacement.

Needs no socket and no running relay: `_on_message` only touches a real `GLib.Bytes` and a
`Soup.WebsocketDataType` value, both constructible headless, and `_catch_up` is driven by a
fake `Soup.Session`-shaped object that returns canned JSON instead of making a real request.
Its delivery runs on a worker thread and lands back via `GLib.idle_add`, so the catch-up tests
pump the real default `GLib.MainContext` to observe it rather than reading `on_item` straight
after the call returns.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import gi

gi.require_version("Soup", "3.0")
gi.require_version("GLib", "2.0")

from gi.repository import GLib, Soup  # noqa: E402
from lios_protocol.wire import ItemSummary  # noqa: E402

from lios_linux.relaylink.stream import STALE_AFTER_SECONDS, StreamConnection  # noqa: E402


def _pump_until(predicate: Callable[[], bool], *, timeout: float = 2.0) -> None:
    """Iterate the default `GLib.MainContext` until `predicate()` is true, or raise.

    Stands in for the real GTK main loop for tests that need a worker thread's
    `GLib.idle_add` callback to actually run.
    """
    deadline = time.monotonic() + timeout
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition not met within timeout")

_ITEM_JSON = (
    b'{"type":"item.new","item":{'
    b'"id":"11111111-1111-1111-1111-111111111111",'
    b'"sender_device_id":"22222222-2222-2222-2222-222222222222",'
    b'"target_device_id":null,'
    b'"size_bytes":42,'
    b'"created_at":"2026-09-03T12:00:00Z"}}'
)

_LIST_JSON = (
    b'[{"id":"33333333-3333-3333-3333-333333333333",'
    b'"sender_device_id":"22222222-2222-2222-2222-222222222222",'
    b'"target_device_id":null,'
    b'"size_bytes":10,'
    b'"created_at":"2026-09-03T13:00:00Z"}]'
)


class _FakeSession:
    """Stands in for `Soup.Session` -- `rest.list_items_since` only ever calls
    `send_and_read` on whatever it is given, so this needs no real network or relay."""

    def __init__(self, response_json: bytes) -> None:
        self._response_json = response_json
        self.requested_urls: list[str] = []

    def send_and_read(self, message: Soup.Message, _cancellable: object) -> GLib.Bytes:
        self.requested_urls.append(message.get_uri().to_string())
        return GLib.Bytes.new(self._response_json)


def _connection() -> tuple[StreamConnection, list[ItemSummary]]:
    received: list[ItemSummary] = []
    connection = StreamConnection(
        relay_url="https://example.invalid",
        device_token="token",
        session=Soup.Session(),
        on_item=received.append,
        get_catch_up_since=lambda: None,  # unused by these message-only tests
    )
    return connection, received


def test_a_real_item_message_is_decoded_and_dispatched() -> None:
    connection, received = _connection()
    connection._on_message(None, Soup.WebsocketDataType.TEXT, GLib.Bytes.new(_ITEM_JSON))
    assert len(received) == 1
    assert str(received[0].id) == "11111111-1111-1111-1111-111111111111"


def test_a_ping_message_is_ignored_rather_than_dispatched() -> None:
    connection, received = _connection()
    connection._on_message(
        None, Soup.WebsocketDataType.TEXT, GLib.Bytes.new(b'{"type":"ping"}')
    )
    assert received == []


def test_a_binary_message_is_ignored() -> None:
    connection, received = _connection()
    connection._on_message(None, Soup.WebsocketDataType.BINARY, GLib.Bytes.new(_ITEM_JSON))
    assert received == []


def test_catch_up_asks_for_the_watermark_at_call_time_not_construction_time() -> None:
    """The whole point of the callback (rather than a value passed once): a caller can move
    the watermark forward between constructing this connection and it actually catching up,
    and the next catch-up must see that new value, not a stale one."""
    fake_session = _FakeSession(b"[]")
    watermark = {"since": "2026-09-03T10:00:00+00:00"}
    connection = StreamConnection(
        relay_url="https://example.invalid",
        device_token="token",
        session=fake_session,
        on_item=lambda _item: None,
        get_catch_up_since=lambda: datetime.fromisoformat(watermark["since"]),
    )

    watermark["since"] = "2026-09-03T14:30:00+00:00"
    connection._catch_up()
    _pump_until(lambda: bool(fake_session.requested_urls))

    query = parse_qs(urlparse(fake_session.requested_urls[0]).query)
    assert query["since"] == ["2026-09-03T14:30:00+00:00"]


def test_catch_up_dispatches_every_item_the_list_returns() -> None:
    fake_session = _FakeSession(_LIST_JSON)
    received: list[ItemSummary] = []
    connection = StreamConnection(
        relay_url="https://example.invalid",
        device_token="token",
        session=fake_session,
        on_item=received.append,
        get_catch_up_since=lambda: datetime.fromisoformat("2026-09-03T00:00:00+00:00"),
    )

    connection._catch_up()
    _pump_until(lambda: bool(received))

    assert len(received) == 1
    assert str(received[0].id) == "33333333-3333-3333-3333-333333333333"


def test_catch_up_returns_before_the_rest_call_completes() -> None:
    """The REST call runs on a worker thread -- `_catch_up` itself must return long before a
    slow relay response arrives, since its caller is the GTK main loop."""
    release = threading.Event()

    class _BlockingSession:
        def send_and_read(self, message: Soup.Message, _cancellable: object) -> GLib.Bytes:
            release.wait(timeout=2.0)
            return GLib.Bytes.new(b"[]")

    connection = StreamConnection(
        relay_url="https://example.invalid",
        device_token="token",
        session=_BlockingSession(),
        on_item=lambda _item: None,
        get_catch_up_since=lambda: datetime.fromisoformat("2026-09-03T00:00:00+00:00"),
    )

    started = time.monotonic()
    connection._catch_up()
    elapsed = time.monotonic() - started

    release.set()
    assert elapsed < 0.5


class _FakeWebsocket:
    """Stands in for a live `Soup.WebsocketConnection`. The watchdog only ever closes one."""

    def __init__(self) -> None:
        self.close_calls = 0

    def close(self, _code: object, _data: object) -> None:
        self.close_calls += 1


def _live_connection() -> tuple[StreamConnection, _FakeWebsocket]:
    """A `StreamConnection` in the state it is in just after a successful connect."""
    connection, _received = _connection()
    socket = _FakeWebsocket()
    connection._stopped = False
    connection._connection = socket  # type: ignore[assignment]
    connection._last_frame_at = time.monotonic()
    return connection, socket


def test_the_watchdog_drops_a_connection_that_has_gone_silent() -> None:
    connection, socket = _live_connection()
    connection._last_frame_at = time.monotonic() - STALE_AFTER_SECONDS - 1

    connection._watchdog_tick()

    assert socket.close_calls == 1
    assert connection._connection is None


def test_the_watchdog_leaves_a_connection_that_is_still_receiving_frames() -> None:
    connection, socket = _live_connection()
    connection._last_frame_at = time.monotonic() - STALE_AFTER_SECONDS + 5

    connection._watchdog_tick()

    assert socket.close_calls == 0
    assert connection._connection is socket


def test_a_ping_counts_as_evidence_the_connection_is_alive() -> None:
    """A ping carries nothing, and is the only thing an idle connection ever sends -- so it
    has to stamp the liveness clock even though it is dispatched nowhere."""
    connection, socket = _live_connection()
    connection._last_frame_at = time.monotonic() - STALE_AFTER_SECONDS - 1

    connection._on_frame(
        connection._generation,
        socket,
        Soup.WebsocketDataType.TEXT,
        GLib.Bytes.new(b'{"type":"ping"}'),
    )
    connection._watchdog_tick()

    assert socket.close_calls == 0
    assert connection._connection is socket


def test_a_late_closed_signal_for_an_abandoned_socket_schedules_no_second_reconnect() -> None:
    """`close` is not synchronous, so the socket the watchdog just gave up on still emits
    `closed` afterwards. Acting on it would schedule a reconnect on top of the one the
    watchdog already scheduled, leaving two connections racing each other."""
    connection, _socket = _live_connection()
    connection._last_frame_at = time.monotonic() - STALE_AFTER_SECONDS - 1
    stale_generation = connection._generation

    connection._watchdog_tick()
    attempts_after_watchdog = connection._attempt
    connection._on_closed(stale_generation)

    assert connection._attempt == attempts_after_watchdog


def test_a_frame_arriving_on_an_abandoned_socket_does_not_keep_it_looking_alive() -> None:
    connection, socket = _live_connection()
    stale_generation = connection._generation
    connection._abandon_connection()
    connection._last_frame_at = 0.0

    connection._on_frame(
        stale_generation,
        socket,
        Soup.WebsocketDataType.TEXT,
        GLib.Bytes.new(b'{"type":"ping"}'),
    )

    assert connection._last_frame_at == 0.0
