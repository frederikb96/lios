"""`org.freedesktop.portal.Flatpak.UpdateMonitor` -- learning that a newer build is already on
disk while this process is still running the one it started with.

An installed Flatpak commit is immutable and stays mounted for the life of a sandbox built
from it, so nothing this process can read from its own filesystem ever changes underneath it
-- installing a new version never touches an already-running instance's view of `/app`, no
matter how the install happened (a real remote update or a bare `flatpak-builder --install`
of a freshly rebuilt one). `CreateUpdateMonitor` is the one supported way around that: it runs
outside this sandbox, in the Flatpak session helper, which can see that the *installed* commit
has moved on regardless.

Only `local-commit` vs. `running-commit` matters here -- whether restarting this process would
run different code than it is running now. `remote-commit` (a real network-available update)
is not a case this app watches for, since it self-hosts no update channel of its own.

Untestable in this environment: needs the Flatpak session helper on the session bus, which
only exists inside a running Flatpak sandbox. `is_stale` holds the only decision this module
makes that does not need one.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

_BUS_NAME = "org.freedesktop.portal.Flatpak"
_OBJECT_PATH = "/org/freedesktop/portal/Flatpak"
_MONITOR_INTERFACE = _BUS_NAME + ".UpdateMonitor"
_HANDLE_TOKEN = "lios_update_monitor"


def is_stale(update_info: dict[str, str]) -> bool:
    """Whether the `UpdateAvailable` signal's payload means a newer build is already
    installed than the one currently running -- i.e. restarting would pick up different code.

    Requires both commits to be genuinely known before calling anything stale: a payload
    missing either key (which the real portal never sends, but nothing here should trust that
    blindly) means "cannot tell", not "yes".
    """
    local_commit = update_info.get("local-commit")
    running_commit = update_info.get("running-commit")
    if not local_commit or not running_commit:
        return False
    return local_commit != running_commit


def watch_for_stale_build(connection: Gio.DBusConnection, *, on_stale: Callable[[], None]) -> None:
    """Ask the Flatpak portal to report if a newer build gets installed while this process
    keeps running, and call `on_stale` -- from the main loop -- the first time `is_stale` says
    so. The object path is predicted from our own connection's mangled unique name and a fixed
    handle token, the same technique `portals.request` uses for the ordinary Request/Response
    portals; `CreateUpdateMonitor` only ever runs once per process, so no collision is possible.
    """
    unique_name = connection.get_unique_name()
    if unique_name is None:
        return  # not a message-bus connection -- nothing to watch
    sender = unique_name.lstrip(":").replace(".", "_")
    monitor_path = f"{_OBJECT_PATH}/update_monitor/{sender}/{_HANDLE_TOKEN}"

    def on_update_available(
        _conn: Gio.DBusConnection,
        _sender_name: str,
        _path: str,
        _iface: str,
        _signal: str,
        params: GLib.Variant,
    ) -> None:
        (update_info,) = params.unpack()
        if is_stale(update_info):
            on_stale()

    connection.signal_subscribe(
        _BUS_NAME,
        _MONITOR_INTERFACE,
        "UpdateAvailable",
        monitor_path,
        None,
        Gio.DBusSignalFlags.NONE,
        on_update_available,
    )
    connection.call(
        _BUS_NAME,
        _OBJECT_PATH,
        _BUS_NAME,
        "CreateUpdateMonitor",
        GLib.Variant("(a{sv})", ({"handle_token": GLib.Variant("s", _HANDLE_TOKEN)},)),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
        lambda conn, res: conn.call_finish(res),
    )
