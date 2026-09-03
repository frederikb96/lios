"""`StreamConnection._on_message` decodes a real `GLib.Bytes`, not `bytes(message)`.

`bytes(some_glib_bytes)` raises `TypeError: cannot convert 'Bytes' object to bytes` -- the
message signal's payload never converts that way, only `.get_data()` does, matching every
other call site in this tree. This is why nothing the phone sent ever reached the laptop, and
why the failure repeated on every keepalive too, since the ping check ran after the broken
conversion.

Needs no socket and no running relay: `_on_message` only touches a real `GLib.Bytes` and a
`Soup.WebsocketDataType` value, both constructible headless.
"""

from __future__ import annotations

import gi

gi.require_version("Soup", "3.0")
gi.require_version("GLib", "2.0")

from gi.repository import GLib, Soup  # noqa: E402
from lios_protocol.wire import ItemSummary  # noqa: E402

from lios_linux.relaylink.stream import StreamConnection  # noqa: E402

_ITEM_JSON = (
    b'{"type":"item.new","item":{'
    b'"id":"11111111-1111-1111-1111-111111111111",'
    b'"sender_device_id":"22222222-2222-2222-2222-222222222222",'
    b'"target_device_id":null,'
    b'"size_bytes":42,'
    b'"created_at":"2026-09-03T12:00:00Z"}}'
)


def _connection() -> tuple[StreamConnection, list[ItemSummary]]:
    received: list[ItemSummary] = []
    connection = StreamConnection(
        relay_url="https://example.invalid",
        device_token="token",
        session=Soup.Session(),
        on_item=received.append,
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
