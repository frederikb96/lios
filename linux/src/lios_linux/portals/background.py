"""`org.freedesktop.portal.Background` -- asking (never assuming) permission to autostart.

`autostart: true` is a documented option key: the portal itself writes the host-side
autostart entry, so this application never needs filesystem access to place one, and GNOME
lists it under Settings -> Applications -> Background Apps, where the user can revoke it at
any time. This is asked once, with a `reason` the consent dialog shows -- never enabled
silently, per the workstation rule against auto-enabling background tasks.

`dbus-activatable` is deliberately false, which is what makes the login launch windowless. A
`DBusActivatable=true` autostart entry is not launched by its `Exec` line at all: the session
calls `org.freedesktop.Application.Activate` on the bus name instead, which reaches
`do_activate` and shows a window -- so the `background` argument written into `commandline`
would never be seen, and every login would open the app in the foreground. With it false the
session runs the command line verbatim, which is the whole point of having one.

Untestable in this environment: needs a running `xdg-desktop-portal-gnome` background backend.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from lios_linux.portals.request import call_request_method  # noqa: E402

_INTERFACE = "org.freedesktop.portal.Background"


def request_autostart(
    connection: Gio.DBusConnection,
    *,
    reason: str,
    command: list[str],
    on_response: Callable[[bool], None],
) -> None:
    """Ask the user for permission to start at login.

    `on_response` receives `True` if the portal reports the request succeeded (response code
    0), `False` for a user decline or any other error -- either way the app continues to run
    normally this session; only future logins are affected.
    """

    def build_parameters(token: str) -> GLib.Variant:
        options = {
            "handle_token": GLib.Variant("s", token),
            "reason": GLib.Variant("s", reason),
            "autostart": GLib.Variant("b", True),
            "commandline": GLib.Variant("as", command),
            "dbus-activatable": GLib.Variant("b", False),
        }
        return GLib.Variant("(sa{sv})", ("", options))

    def on_portal_response(response_code: int, _results: dict[str, object]) -> None:
        on_response(response_code == 0)

    call_request_method(
        connection,
        interface=_INTERFACE,
        method="RequestBackground",
        build_parameters=build_parameters,
        on_response=on_portal_response,
    )
