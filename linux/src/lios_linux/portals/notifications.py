"""Desktop notifications for an item arriving, via `Gio.Notification`.

One notification, one action, for every kind: the default action -- the banner's click target,
the only genuinely one-click affordance GNOME offers -- opens the window with that item
selected. Nothing here offers Copy or Save directly on the banner, because a notification
action arrives at the app over D-Bus with no input event behind it, which is exactly the
trigger `Gdk.Clipboard` cannot honour. Opening the window first is what turns the button click
or accelerator that follows into a genuine in-window input event.

`Gio.Application.send_notification` routes through the Notification portal automatically when
sandboxed -- nothing here talks to the portal directly. Untestable in this environment: needs
a running notification daemon (GNOME Shell) to display anything.
"""

from __future__ import annotations

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

ACTION_COPY_ITEM = "app.copy-item"
ACTION_OPEN_ITEM = "app.open-item"
ACTION_SAVE_ITEM = "app.save-item"

_TITLE_BY_KIND = {
    "text": "New text from your phone",
    "image": "New image from your phone",
    "file": "New file from your phone",
}


def build_item_arrived_notification(
    item_id: str, *, kind: str, filename: str | None
) -> Gio.Notification:
    """One item arrived: the default action opens the window with it selected."""
    notification = Gio.Notification.new(_TITLE_BY_KIND.get(kind, "New item from your phone"))
    notification.set_body(filename or "Tap to view")
    notification.set_default_action_and_target(ACTION_OPEN_ITEM, GLib.Variant("s", item_id))
    return notification


def withdraw(app: Gio.Application, item_id: str) -> None:
    """Remove a notification once its item has been handled -- keyed by item id."""
    app.withdraw_notification(item_id)
