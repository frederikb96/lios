"""The request/response pattern shared by most `org.freedesktop.portal.*` methods.

A method call returns a `Request` object path immediately; the actual answer -- whether the
user approved it, and any results -- arrives later as a `Response` signal on that path. This
module predicts the path from a caller-chosen `handle_token` (per the portal spec: `/org/
freedesktop/portal/desktop/request/SENDER/TOKEN`, with the caller's own bus name mangled into
`SENDER`), subscribes to it before making the call, and unsubscribes itself once the response
arrives.

Untestable in this environment: needs a running `xdg-desktop-portal` on the session bus.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"


def _new_handle_token() -> str:
    """A caller-chosen token unique enough not to collide with a concurrent request."""
    return "lios_" + secrets.token_hex(8)


def call_request_method(
    connection: Gio.DBusConnection,
    *,
    interface: str,
    method: str,
    build_parameters: Callable[[str], GLib.Variant],
    on_response: Callable[[int, dict[str, Any]], None],
) -> None:
    """Call a portal method that answers via the Request/Response pattern.

    `build_parameters` receives the handle token this call will use and must fold it into the
    options it returns, as `{"handle_token": GLib.Variant("s", token), ...}` -- the response
    subscription below only arrives at the right path if the token in the call matches.

    `on_response` is invoked exactly once, from the main loop, with the numeric response code
    (0 succeeded, 1 the user cancelled, 2 another error) and the results dict.
    """
    token = _new_handle_token()
    sender = connection.get_unique_name().lstrip(":").replace(".", "_")
    request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    subscription_ids: list[int] = []

    def _on_signal(
        _conn: Gio.DBusConnection,
        _sender_name: str,
        _path: str,
        _iface: str,
        _signal: str,
        params: GLib.Variant,
    ) -> None:
        response_code, results = params.unpack()
        connection.signal_unsubscribe(subscription_ids[0])
        on_response(response_code, results)

    subscription_ids.append(
        connection.signal_subscribe(
            PORTAL_BUS_NAME,
            "org.freedesktop.portal.Request",
            "Response",
            request_path,
            None,
            Gio.DBusSignalFlags.NONE,
            _on_signal,
        )
    )

    connection.call(
        PORTAL_BUS_NAME,
        PORTAL_OBJECT_PATH,
        interface,
        method,
        build_parameters(token),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
        lambda conn, res: conn.call_finish(res),
    )
