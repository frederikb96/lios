"""Blocking REST calls against the relay, on `Soup.Session`.

Every call here blocks the calling thread until the response arrives. That is fine for the two
places this module is used: a pairing flow the user is already waiting on, and a one-off send
triggered from a global shortcut or the UI -- both already run off the GTK main thread (see
`app.py`'s worker-thread dispatch). The one long-lived connection this application holds, the
`/api/stream` WebSocket, is `stream.py` instead, which is async and lives on the main loop for
as long as the app runs.

Untestable in this environment without a running relay to call. `relaylink.endpoints` (the URL
and header construction this module uses under every call) is unit-tested on its own.
"""

from __future__ import annotations

import json
from datetime import datetime

import gi

gi.require_version("Soup", "3.0")
gi.require_version("GLib", "2.0")

from gi.repository import GLib, Soup  # noqa: E402
from lios_protocol.wire import (  # noqa: E402
    DeviceBootstrap,
    DevicePaired,
    ItemCreated,
    ItemSummary,
    PairingRedeem,
    PairingSessionCreated,
)

from lios_linux.relaylink import endpoints  # noqa: E402


class RelayError(RuntimeError):
    """A relay call failed -- a non-2xx status, or a transport-level error."""


def _message(method: str, url: str, *, headers: dict[str, str], body: bytes | None) -> Soup.Message:
    message = Soup.Message.new(method, url)
    if message is None:
        raise RelayError(f"{method} {url}: malformed URL")
    for key, value in headers.items():
        message.get_request_headers().append(key, value)
    if body is not None:
        message.set_request_body_from_bytes(
            headers.get("Content-Type", "application/octet-stream"), GLib.Bytes.new(body)
        )
    return message


def _send(session: Soup.Session, message: Soup.Message) -> bytes:
    """Send `message` to completion and return its body, raising `RelayError` on failure."""
    try:
        body = session.send_and_read(message, None)
    except GLib.Error as exc:
        raise RelayError(f"{message.get_method()} {message.get_uri().to_string()}: {exc}") from exc
    status = message.get_status()
    data = (body.get_data() or b"") if body else b""
    if status >= 300:
        detail = data.decode("utf-8", errors="replace")
        raise RelayError(
            f"{message.get_method()} {message.get_uri().to_string()} -> {status}: {detail[:200]}"
        )
    return data


def bootstrap_first_device(
    session: Soup.Session, *, relay_url: str, display_name: str
) -> DevicePaired:
    """`POST /api/devices/bootstrap` -- register the very first device in an empty fleet.

    Raises:
        RelayError: a device is already registered (403), or the call otherwise failed.
    """
    body = DeviceBootstrap(platform="linux", display_name=display_name).model_dump_json().encode(
        "utf-8"
    )
    message = _message(
        "POST", endpoints.bootstrap_url(relay_url), headers={"Content-Type": "application/json"},
        body=body,
    )
    return DevicePaired.model_validate_json(_send(session, message))


def create_pairing_session(
    session: Soup.Session, *, relay_url: str, device_token: str
) -> PairingSessionCreated:
    """`POST /api/devices/pairing-sessions` -- mint a code on behalf of an already-paired device."""
    message = _message(
        "POST",
        endpoints.pairing_sessions_url(relay_url),
        headers=endpoints.auth_header(device_token),
        body=None,
    )
    return PairingSessionCreated.model_validate_json(_send(session, message))


def pair_device(
    session: Soup.Session, *, relay_url: str, pairing_code: str, display_name: str
) -> DevicePaired:
    """`POST /api/devices/pair` -- redeem a code for this new device's own token."""
    body = PairingRedeem(
        pairing_code=pairing_code, platform="linux", display_name=display_name
    ).model_dump_json().encode("utf-8")
    message = _message(
        "POST",
        endpoints.pair_url(relay_url),
        headers={"Content-Type": "application/json"},
        body=body,
    )
    return DevicePaired.model_validate_json(_send(session, message))


def create_item(
    session: Soup.Session,
    *,
    relay_url: str,
    device_token: str,
    item_id: str,
    sealed_blob: bytes,
    target_device_id: str | None = None,
    sealed_preview: bytes | None = None,
) -> ItemCreated:
    """`POST /api/items` -- upload one sealed blob, raw.

    `item_id` must be the same id sealed into `sealed_blob`'s AEAD associated data (see
    `relaylink.item_codec`) -- the relay cannot assign one after the fact without making the
    blob the caller just sealed unopenable.
    """
    headers = endpoints.create_item_headers(
        device_token=device_token,
        item_id=item_id,
        content_length=len(sealed_blob),
        sealed_preview=sealed_preview,
    )
    url = endpoints.items_url(relay_url, target_device_id=target_device_id)
    message = _message("POST", url, headers=headers, body=sealed_blob)
    return ItemCreated.model_validate_json(_send(session, message))


def get_item(session: Soup.Session, *, relay_url: str, device_token: str, item_id: str) -> bytes:
    """`GET /api/items/{id}` -- fetch one item's sealed blob, raw."""
    message = _message(
        "GET",
        endpoints.item_url(relay_url, item_id),
        headers=endpoints.auth_header(device_token),
        body=None,
    )
    return _send(session, message)


def list_items_since(
    session: Soup.Session, *, relay_url: str, device_token: str, since: datetime
) -> list[ItemSummary]:
    """`GET /api/items?since=...` -- the catch-up list for time spent disconnected."""
    message = _message(
        "GET",
        endpoints.items_since_url(relay_url, since),
        headers=endpoints.auth_header(device_token),
        body=None,
    )
    payload = _send(session, message)
    return [ItemSummary.model_validate(entry) for entry in json.loads(payload)]


def ack_item(session: Soup.Session, *, relay_url: str, device_token: str, item_id: str) -> None:
    """`DELETE /api/items/{id}` -- confirm this device has taken the item."""
    message = _message(
        "DELETE",
        endpoints.item_url(relay_url, item_id),
        headers=endpoints.auth_header(device_token),
        body=None,
    )
    _send(session, message)
