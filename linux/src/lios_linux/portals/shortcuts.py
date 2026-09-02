"""`org.freedesktop.portal.GlobalShortcuts` -- send-clipboard and send-file, bindable from
GNOME Settings.

Two calls in sequence, each following the Request pattern: `CreateSession` gets a session
handle, then `BindShortcuts` registers the shortcut ids against it and shows GNOME's one-time
consent/rebind dialog. After that, every press arrives as an `Activated` signal on this
interface directly (not through another Request), carrying the shortcut id and an activation
token this application passes on to `wl-copy`/`wl-paste` so their clipboard touch is a
sanctioned Wayland activation rather than the zero-timestamp fallback.

Exported as the good UX, with the CLI (`cli.py`) always present as the fallback for any
desktop without a GlobalShortcuts backend -- GNOME's own backend only exists from GNOME 48,
and its activation token only arrives correctly from GNOME 50 (spec row 66; report
055c37e1-f508-4d6c-b63f-2ae31ff8bdfc, requirement 4).

Untestable in this environment: needs a running `xdg-desktop-portal-gnome` GlobalShortcuts
backend.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from lios_linux.portals.request import call_request_method  # noqa: E402

_INTERFACE = "org.freedesktop.portal.GlobalShortcuts"

#: The two shortcuts this application registers, and the label GNOME Settings shows for each.
SHORTCUT_SEND_CLIPBOARD = "send-clipboard"
SHORTCUT_SEND_FILE = "send-file"

_SHORTCUT_DESCRIPTIONS = {
    SHORTCUT_SEND_CLIPBOARD: "Send the current clipboard to a paired phone",
    SHORTCUT_SEND_FILE: "Send a chosen file to a paired phone",
}


def create_session_and_bind(
    connection: Gio.DBusConnection,
    *,
    on_bound: Callable[[str], None],
    on_error: Callable[[str], None],
) -> None:
    """Create a GlobalShortcuts session and bind both shortcuts against it.

    `on_bound` receives the session handle once binding succeeds -- callers do not need it
    afterwards (the `Activated` signal below carries the shortcut id directly), but it is
    handed back in case a future rebind or session teardown needs it.
    """

    def build_create_session_parameters(token: str) -> GLib.Variant:
        options = {"handle_token": GLib.Variant("s", token)}
        return GLib.Variant("(a{sv})", (options,))

    def on_session_created(response_code: int, results: dict[str, object]) -> None:
        if response_code != 0 or "session_handle" not in results:
            on_error(f"GlobalShortcuts CreateSession failed: response {response_code}")
            return
        session_handle = str(results["session_handle"])
        _bind_shortcuts(connection, session_handle, on_bound=on_bound, on_error=on_error)

    call_request_method(
        connection,
        interface=_INTERFACE,
        method="CreateSession",
        build_parameters=build_create_session_parameters,
        on_response=on_session_created,
    )


def _bind_shortcuts(
    connection: Gio.DBusConnection,
    session_handle: str,
    *,
    on_bound: Callable[[str], None],
    on_error: Callable[[str], None],
) -> None:
    def build_bind_parameters(token: str) -> GLib.Variant:
        shortcuts = [
            (shortcut_id, {"description": GLib.Variant("s", description)})
            for shortcut_id, description in _SHORTCUT_DESCRIPTIONS.items()
        ]
        options = {"handle_token": GLib.Variant("s", token)}
        return GLib.Variant(
            "(oa(sa{sv})sa{sv})", (session_handle, shortcuts, "", options)
        )

    def on_bind_response(response_code: int, _results: dict[str, object]) -> None:
        if response_code != 0:
            on_error(f"GlobalShortcuts BindShortcuts failed: response {response_code}")
            return
        on_bound(session_handle)

    call_request_method(
        connection,
        interface=_INTERFACE,
        method="BindShortcuts",
        build_parameters=build_bind_parameters,
        on_response=on_bind_response,
    )


def subscribe_activated(
    connection: Gio.DBusConnection,
    *,
    on_activated: Callable[[str, str, str | None], None],
) -> int:
    """Listen for every future shortcut press.

    `on_activated` receives the shortcut id, the timestamp (unused by this application), and
    the activation token -- pass the token through to `wl-copy`/`wl-paste` as
    `$XDG_ACTIVATION_TOKEN`.

    Returns the subscription id, for `Gio.DBusConnection.signal_unsubscribe` at shutdown.
    """

    def _on_signal(
        _conn: Gio.DBusConnection,
        _sender_name: str,
        _path: str,
        _iface: str,
        _signal: str,
        params: GLib.Variant,
    ) -> None:
        _session_handle, shortcut_id, _timestamp, options = params.unpack()
        activation_token = options.get("activation_token")
        on_activated(shortcut_id, _timestamp, activation_token)

    return int(
        connection.signal_subscribe(
            "org.freedesktop.portal.Desktop",
            _INTERFACE,
            "Activated",
            "/org/freedesktop/portal/desktop",
            None,
            Gio.DBusSignalFlags.NONE,
            _on_signal,
        )
    )
