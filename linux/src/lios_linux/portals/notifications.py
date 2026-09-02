"""Desktop notifications for an item arriving, via `Gio.Notification`.

GNOME renders at most three action buttons, and only once the notification is expanded
(gnome-shell `js/ui/messageList.js`: `MAX_NOTIFICATION_BUTTONS = 3`, and the action area is
only visible when `expanded`). The banner body's click target -- the notification's *default*
action -- is the only genuinely one-click affordance, so the important behaviour goes there:
a text item's default action copies it and withdraws the notification with nothing left to
dismiss; an image or file's default action opens the window on that item with Copy and Save
also offered as notification buttons for anyone who expands it (report
055c37e1-f508-4d6c-b63f-2ae31ff8bdfc, requirement 2).

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


def build_text_arrived_notification(item_id: str) -> Gio.Notification:
    """A text item: the default action copies it and withdraws the notification."""
    notification = Gio.Notification.new("New text from your phone")
    notification.set_body("Click to copy")
    notification.set_default_action_and_target(ACTION_COPY_ITEM, GLib.Variant("s", item_id))
    return notification


def build_media_arrived_notification(
    item_id: str, *, kind: str, filename: str | None
) -> Gio.Notification:
    """An image or file item: the default action opens the window on it, with Copy and Save
    also offered as notification buttons for anyone who expands the banner."""
    title = "New image from your phone" if kind == "image" else "New file from your phone"
    notification = Gio.Notification.new(title)
    notification.set_body(filename or "Tap to view")
    notification.set_default_action_and_target(ACTION_OPEN_ITEM, GLib.Variant("s", item_id))
    notification.add_button_with_target("Copy", ACTION_COPY_ITEM, GLib.Variant("s", item_id))
    notification.add_button_with_target("Save", ACTION_SAVE_ITEM, GLib.Variant("s", item_id))
    return notification


def withdraw(app: Gio.Application, item_id: str) -> None:
    """Remove a notification once its item has been handled -- keyed by item id."""
    app.withdraw_notification(item_id)
