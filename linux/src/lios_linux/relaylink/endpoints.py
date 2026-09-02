"""Pure URL and header construction against the relay's REST/WebSocket surface.

Kept free of any network call so the shape of every request is unit-testable without a
running relay. `lios_relay.api.*` (in the sibling `relay/` package) is the authority on the
routes themselves; this module only builds what a caller needs to hit them.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote, urlencode


def _base(relay_url: str) -> str:
    return relay_url.rstrip("/")


def items_url(relay_url: str, *, target_device_id: str | None = None) -> str:
    """`POST /api/items`, optionally narrowed to one recipient device."""
    url = f"{_base(relay_url)}/api/items"
    if target_device_id:
        url += "?" + urlencode({"target_device_id": target_device_id})
    return url


def item_url(relay_url: str, item_id: str) -> str:
    """`GET`/`DELETE /api/items/{id}`."""
    return f"{_base(relay_url)}/api/items/{quote(item_id, safe='')}"


def items_since_url(relay_url: str, since: datetime) -> str:
    """`GET /api/items?since=...`, the catch-up list for a client that was offline."""
    return f"{_base(relay_url)}/api/items?" + urlencode({"since": since.isoformat()})


def stream_url(relay_url: str) -> str:
    """`GET /api/stream`, as the `ws://`/`wss://` URL a WebSocket client connects to.

    Raises:
        ValueError: `relay_url` is neither an `http://` nor an `https://` URL.
    """
    base = _base(relay_url)
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :] + "/api/stream"
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :] + "/api/stream"
    raise ValueError(f"relay_url must start with http:// or https://, got {relay_url!r}")


def bootstrap_url(relay_url: str) -> str:
    """`POST /api/devices/bootstrap` -- registering the very first device in an empty fleet."""
    return f"{_base(relay_url)}/api/devices/bootstrap"


def pairing_sessions_url(relay_url: str) -> str:
    """`POST /api/devices/pairing-sessions`."""
    return f"{_base(relay_url)}/api/devices/pairing-sessions"


def pair_url(relay_url: str) -> str:
    """`POST /api/devices/pair`."""
    return f"{_base(relay_url)}/api/devices/pair"


def push_token_url(relay_url: str, device_id: str) -> str:
    """`POST /api/devices/{id}/push-token`."""
    return f"{_base(relay_url)}/api/devices/{quote(device_id, safe='')}/push-token"


def auth_header(device_token: str) -> dict[str, str]:
    """The bearer-token `Authorization` header every endpoint but pairing itself requires."""
    return {"Authorization": f"Bearer {device_token}"}
