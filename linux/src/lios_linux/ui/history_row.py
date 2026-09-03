"""One row in the history list: an icon by kind, a preview, a timestamp, and its actions.

Untestable in this environment: needs a live display connection.
"""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("GLib", "2.0")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from lios_linux.history.models import HistoryItem, ItemKind  # noqa: E402

_ICON_BY_KIND = {
    ItemKind.TEXT: "edit-copy-symbolic",
    ItemKind.IMAGE: "image-x-generic-symbolic",
    ItemKind.FILE: "text-x-generic-symbolic",
}


class HistoryRow(Adw.ActionRow):
    """Wraps one `HistoryItem`.

    Text and image items offer Copy; image and file items offer Save -- a file cannot
    meaningfully go on the clipboard as content, so it never gets a Copy button.
    `supports_copy`/`supports_save` are computed once here and read back by the window's
    keyboard accelerators, so the same rule is never re-derived a second time and cannot drift
    from what the buttons actually show.
    """

    def __init__(self, item: HistoryItem) -> None:
        super().__init__()
        self.item_id = item.id
        self.supports_copy = item.kind != ItemKind.FILE
        self.supports_save = item.kind != ItemKind.TEXT
        self.set_title(item.preview or item.filename or item.kind.value)
        self.set_subtitle(item.created_at.strftime("%Y-%m-%d %H:%M"))
        self.add_prefix(Gtk.Image.new_from_icon_name(_ICON_BY_KIND[item.kind]))

        if self.supports_copy:
            copy_button = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER)
            copy_button.set_action_name("app.copy-item")
            copy_button.set_action_target_value(GLib.Variant("s", item.id))
            self.add_suffix(copy_button)

        if self.supports_save:
            save_button = Gtk.Button(icon_name="document-save-symbolic", valign=Gtk.Align.CENTER)
            save_button.set_action_name("app.save-item")
            save_button.set_action_target_value(GLib.Variant("s", item.id))
            self.add_suffix(save_button)
