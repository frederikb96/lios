"""The LIOS window: history, drag-and-drop, typed text, preferences, and pairing.

Created on demand by `app.py`'s `_show_window` and destroyed on close, so the resident
footprint falls back to the headless baseline between uses. The one place this application
uses native `Gdk.Clipboard` at all is implicit here: none of it -- drag-and-drop and the text
entry are GTK's own input paths, not a clipboard read, so they carry no serial problem in the
first place (see `lios_linux.clipboard` for where the real distinction is).

Untestable in this environment: needs a live display connection.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")
gi.require_version("GObject", "2.0")

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from lios_linux.history.store import HistoryStore  # noqa: E402
from lios_linux.relaylink import pairing_flow  # noqa: E402
from lios_linux.relaylink.rest import RelayError  # noqa: E402
from lios_linux.ui.history_row import HistoryRow  # noqa: E402
from lios_linux.ui.pairing_view import QrCodeWidget  # noqa: E402
from lios_linux.ui.preferences import LiosPreferencesDialog  # noqa: E402

logger = logging.getLogger(__name__)


class LiosWindow(Adw.ApplicationWindow):
    """The one window this application ever shows."""

    def __init__(self, *, application: Any, history: HistoryStore) -> None:
        super().__init__(application=application, default_width=420, default_height=560)
        self._history = history
        self._rows: dict[str, HistoryRow] = {}

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append("Pair a new device", "win.pair")
        menu.append("Preferences", "win.preferences")
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)
        toolbar_view.add_top_bar(header)

        self._list_box = Gtk.ListBox(
            css_classes=["boxed-list"], margin_top=12, margin_start=12, margin_end=12
        )
        scrolled = Gtk.ScrolledWindow(vexpand=True, child=self._list_box)

        self._entry = Gtk.Entry(
            placeholder_text="Type something to send...",
            margin_start=12,
            margin_end=12,
            margin_bottom=12,
            margin_top=6,
        )
        self._entry.connect("activate", self._on_entry_activate)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(scrolled)
        content.append(self._entry)
        toolbar_view.set_content(content)
        self.set_content(toolbar_view)

        self._install_drop_target()
        self._install_actions()
        self.reload()

    def _install_actions(self) -> None:
        preferences_action = Gio.SimpleAction.new("preferences", None)
        preferences_action.connect("activate", self._on_preferences)
        self.add_action(preferences_action)

        pair_action = Gio.SimpleAction.new("pair", None)
        pair_action.connect("activate", self._on_pair)
        self.add_action(pair_action)

    def _install_drop_target(self) -> None:
        drop_target = Gtk.DropTarget.new(GObject.TYPE_NONE, Gdk.DragAction.COPY)
        drop_target.set_gtypes([Gdk.FileList, Gdk.Texture, GObject.TYPE_STRING])
        drop_target.connect("drop", self._on_drop)
        self.add_controller(drop_target)

    def _on_drop(self, _target: Gtk.DropTarget, value: Any, _x: float, _y: float) -> bool:
        app = self.get_application()
        if isinstance(value, Gdk.FileList):
            for file in value.get_files():
                path = file.get_path()
                if path:
                    app.send_file(path)
            return True
        if isinstance(value, Gdk.Texture):
            app.upload("image", value.save_to_png_bytes().get_data(), content_type="image/png")
            return True
        if isinstance(value, str):
            app.upload("text", value.encode("utf-8"))
            return True
        return False

    def _on_entry_activate(self, entry: Gtk.Entry) -> None:
        text = entry.get_text()
        if not text:
            return
        self.get_application().upload("text", text.encode("utf-8"))
        entry.set_text("")

    def _on_preferences(self, _action: Gio.SimpleAction, _param: None) -> None:
        LiosPreferencesDialog(app=self.get_application()).present(self)

    def _on_pair(self, _action: Gio.SimpleAction, _param: None) -> None:
        app = self.get_application()

        def worker() -> None:
            try:
                uri = pairing_flow.generate_pairing_qr(
                    relay_url=app.config.relay_url, session=app.soup_session
                )
            except RelayError:
                logger.exception("could not generate a pairing code")
                return
            GLib.idle_add(self._show_pairing_dialog, uri)

        threading.Thread(target=worker, daemon=True).start()

    def _show_pairing_dialog(self, uri: str) -> bool:
        dialog = Adw.Dialog(title="Scan with the LIOS iOS app")
        dialog.set_child(QrCodeWidget(uri))
        dialog.present(self)
        return bool(GLib.SOURCE_REMOVE)

    def reload(self) -> None:
        """Re-populate the list from history. Called on show, and whenever history changes."""
        while (child := self._list_box.get_first_child()) is not None:
            self._list_box.remove(child)
        self._rows.clear()
        for item in self._history.list_recent():
            row = HistoryRow(item)
            self._rows[item.id] = row
            self._list_box.append(row)

    def select_item(self, item_id: str) -> None:
        """Scroll to and select the row for `item_id`, reloading first if not yet shown."""
        if item_id not in self._rows:
            self.reload()
        row = self._rows.get(item_id)
        if row is not None:
            self._list_box.select_row(row)
