"""The LIOS window: onboarding, history, drag-and-drop, paste-to-send, and receiving.

Created once by `app.py`'s `show_window` and hidden (never destroyed) on close, so the
resident footprint stays low between uses while reopening is instant and keeps its state.
Every clipboard touch in this file happens inside this window while it has focus, in
response to an input event the app itself received -- a paste, a click, an accelerator -- which
is exactly what satisfies mutter's clipboard gate with no helper process (see
`lios_linux.clipboard`).

Untestable in this environment: needs a live display connection.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any, cast

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gio", "2.0")
gi.require_version("GObject", "2.0")

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from lios_linux import keyring  # noqa: E402
from lios_linux.clipboard.priority import ClipboardKind, choose_read_type  # noqa: E402
from lios_linux.history.store import HistoryStore  # noqa: E402
from lios_linux.portals import notifications  # noqa: E402
from lios_linux.relaylink import pairing_flow  # noqa: E402
from lios_linux.relaylink.rest import RelayError  # noqa: E402
from lios_linux.ui.history_row import HistoryRow  # noqa: E402
from lios_linux.ui.keyring_unavailable_view import KeyringUnavailableView  # noqa: E402
from lios_linux.ui.onboarding import OnboardingView  # noqa: E402
from lios_linux.ui.pairing_view import QrCodeWidget  # noqa: E402
from lios_linux.ui.preferences import LiosPreferencesDialog  # noqa: E402

if TYPE_CHECKING:
    from lios_linux.app import LiosApplication

logger = logging.getLogger(__name__)


class LiosWindow(Adw.ApplicationWindow):
    """The one window this application ever shows.

    Its content is decided fresh every time the window is shown (not just once at
    construction, since pairing can complete while the window happens to be closed), from
    `keyring.pairing_status()` folded through `keyring.resolve_pairing_status()`: the history
    list once paired, `OnboardingView` once confirmed not paired, and `KeyringUnavailableView`
    whenever the keyring cannot currently say which -- never the onboarding view on the
    strength of an error, since its "claim this relay" path is destructive if this device
    was in fact already paired.
    """

    def __init__(self, *, application: Any, history: HistoryStore) -> None:
        super().__init__(application=application, default_width=420, default_height=560)
        self._history = history
        self._rows: dict[str, HistoryRow] = {}

        self._toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append("Pair a new device", "win.pair")
        menu.append("Preferences", "win.preferences")
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)
        self._toolbar_view.add_top_bar(header)
        self.set_content(self._toolbar_view)

        self._list_box = Gtk.ListBox(
            css_classes=["boxed-list"], margin_top=12, margin_start=12, margin_end=12
        )
        scrolled = Gtk.ScrolledWindow(vexpand=True, child=self._list_box)

        self._entry = Gtk.Entry(
            placeholder_text="Type something to send...", hexpand=True
        )
        self._entry.connect("activate", self._on_entry_activate)

        file_picker_button = Gtk.Button(
            icon_name="document-open-symbolic", valign=Gtk.Align.CENTER
        )
        file_picker_button.set_tooltip_text("Choose a file to send")
        file_picker_button.connect("clicked", self._on_choose_file_clicked)

        send_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            margin_start=12,
            margin_end=12,
            margin_bottom=12,
            margin_top=6,
        )
        send_row.append(self._entry)
        send_row.append(file_picker_button)

        self._history_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._history_content.append(scrolled)
        self._history_content.append(send_row)

        self._install_drop_target()
        self._install_key_controller()
        self._install_actions()
        self.refresh()

    def _app(self) -> "LiosApplication":
        return cast("LiosApplication", self.get_application())

    def refresh(self) -> None:
        """Show whichever of history, onboarding or "can't reach the keyring" now applies,
        and reload either way.

        Called at construction, after pairing completes, and after a keyring unlock attempt
        from `KeyringUnavailableView` -- the pairing status itself can only change at those
        moments. A history change alone does not call this: see `notify_history_changed`,
        `select_item` and `focus_send_and_select_newest` for what keeps the list itself
        correct on every other occasion.
        """
        status = keyring.resolve_pairing_status(
            keyring.pairing_status(), history_has_items=self._history.has_any()
        )
        if status is keyring.PairingStatus.PAIRED:
            self._toolbar_view.set_content(self._history_content)
            self._reload_history()
        elif status is keyring.PairingStatus.UNAVAILABLE:
            unavailable = KeyringUnavailableView(on_retry=self.refresh)
            self._toolbar_view.set_content(unavailable.widget)
        else:
            onboarding = OnboardingView(app=self.get_application(), on_paired=self._on_paired)
            self._toolbar_view.set_content(onboarding.widget)

    def _on_paired(self, *, show_qr: bool) -> None:
        self._app().on_paired()
        self.refresh()
        if show_qr:
            self._generate_and_show_pairing_qr()

    def _install_actions(self) -> None:
        preferences_action = Gio.SimpleAction.new("preferences", None)
        preferences_action.connect("activate", self._on_preferences)
        self.add_action(preferences_action)

        pair_action = Gio.SimpleAction.new("pair", None)
        pair_action.connect("activate", self._on_pair_action)
        self.add_action(pair_action)

    # -- Receiving: keyboard accelerators for the selected history row ------------------------

    def _install_key_controller(self) -> None:
        """Capture phase, so Ctrl+V is seen here before the focused child (the text entry)
        would otherwise consume it as an ordinary text paste."""
        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)

    def _on_key_pressed(
        self, _controller: Gtk.EventControllerKey, keyval: int, _keycode: int, state: Any
    ) -> bool:
        if not bool(state & Gdk.ModifierType.CONTROL_MASK):
            return False
        if keyval in (Gdk.KEY_v, Gdk.KEY_V):
            self._paste_and_send()
            return True
        if self.get_focus() is self._entry:
            return False  # never steal Ctrl+C/Ctrl+S from ordinary text editing
        if keyval in (Gdk.KEY_c, Gdk.KEY_C):
            return self._activate_selected_item(notifications.ACTION_COPY_ITEM)
        if keyval in (Gdk.KEY_s, Gdk.KEY_S):
            return self._activate_selected_item(notifications.ACTION_SAVE_ITEM)
        return False

    def _activate_selected_item(self, action_name: str) -> bool:
        """The button-click equivalent for the currently selected row -- confirmed correct
        from GDK's source for a button click; a keyboard accelerator carries its own fresh
        press serial and should behave identically, but that is unverified on hardware."""
        selected = self._list_box.get_selected_row()
        if selected is None:
            return False
        row = cast(HistoryRow, selected)  # the list box holds nothing else
        if action_name == notifications.ACTION_COPY_ITEM and not row.supports_copy:
            return False
        if action_name == notifications.ACTION_SAVE_ITEM and not row.supports_save:
            return False
        self._app().activate_action(
            action_name.removeprefix("app."), GLib.Variant("s", row.item_id)
        )
        return True

    # -- Sending: drag-and-drop, paste, typed text, and a file picker -------------------------

    def _install_drop_target(self) -> None:
        # PyGObject-stubs types both calls' GType arguments as `type[Any]`; a GType constant
        # is the correct argument per the real GTK API (`gtk_drop_target_new`/`_set_gtypes`).
        drop_target = Gtk.DropTarget.new(GObject.TYPE_NONE, Gdk.DragAction.COPY)  # type: ignore[arg-type]
        drop_target.set_gtypes([Gdk.FileList, Gdk.Texture, GObject.TYPE_STRING])  # type: ignore[list-item]
        drop_target.connect("drop", self._on_drop)
        self.add_controller(drop_target)

    def _on_drop(self, _target: Gtk.DropTarget, value: Any, _x: float, _y: float) -> bool:
        return self._send_value(value)

    def _paste_and_send(self) -> None:
        """Ctrl+V anywhere in the window: ask the clipboard what it offers, pick the richest
        useful form by the same ordered priority drag-and-drop already uses, and read it."""
        clipboard = self.get_display().get_clipboard()
        mime_types = list(clipboard.get_formats().get_mime_types() or [])
        choice = choose_read_type(mime_types)
        if choice is None:
            return
        if choice.kind == ClipboardKind.IMAGE:
            clipboard.read_texture_async(None, self._on_paste_texture)
        elif choice.kind in (ClipboardKind.FILE_TRANSFER, ClipboardKind.URI_LIST):
            clipboard.read_value_async(
                Gdk.FileList, GLib.PRIORITY_DEFAULT, None, self._on_paste_file_list
            )
        else:
            clipboard.read_text_async(None, self._on_paste_text)

    def _on_paste_texture(self, clipboard: Gdk.Clipboard, result: Gio.AsyncResult) -> None:
        try:
            texture = clipboard.read_texture_finish(result)
        except GLib.Error:
            logger.warning("paste: could not read an image from the clipboard")
            return
        if texture is not None:
            self._send_value(texture)

    def _on_paste_file_list(self, clipboard: Gdk.Clipboard, result: Gio.AsyncResult) -> None:
        try:
            value = clipboard.read_value_finish(result)
        except GLib.Error:
            logger.warning("paste: could not read files from the clipboard")
            return
        self._send_value(value)

    def _on_paste_text(self, clipboard: Gdk.Clipboard, result: Gio.AsyncResult) -> None:
        try:
            text = clipboard.read_text_finish(result)
        except GLib.Error:
            logger.warning("paste: could not read text from the clipboard")
            return
        if text:
            self._send_value(text)

    def _send_value(self, value: Any) -> bool:
        """Shared by drag-and-drop and paste -- both ultimately hand this the same three GTK
        content shapes, whichever path they arrived by."""
        app = self._app()
        if isinstance(value, Gdk.FileList):
            for file in value.get_files():
                path = file.get_path()
                if path:
                    app.send_file(path)
            return True
        if isinstance(value, Gdk.Texture):
            png_bytes = value.save_to_png_bytes().get_data() or b""
            app.upload("image", png_bytes, content_type="image/png")
            return True
        if isinstance(value, str):
            app.upload("text", value.encode("utf-8"))
            return True
        return False

    def _on_entry_activate(self, entry: Gtk.Entry) -> None:
        text = entry.get_text()
        if not text:
            return
        self._app().upload("text", text.encode("utf-8"))
        entry.set_text("")

    def _on_choose_file_clicked(self, _button: Gtk.Button) -> None:
        Gtk.FileDialog().open(self, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return  # cancelled, or the dialog failed -- either way, nothing to send
        path = file.get_path() if file is not None else None
        if path:
            self._app().send_file(path)

    # -- Preferences / pairing menu ------------------------------------------------------------

    def _on_preferences(self, _action: Gio.SimpleAction, _param: None) -> None:
        LiosPreferencesDialog(app=self.get_application()).present(self)

    def _on_pair_action(self, _action: Gio.SimpleAction, _param: None) -> None:
        self._generate_and_show_pairing_qr()

    def _generate_and_show_pairing_qr(self) -> None:
        app = self._app()

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

    # -- History list, and being made "ready" from the outside --------------------------------

    def _reload_history(self) -> None:
        """Rebuild every row from `self._history` -- the one place that does, so every
        caller (construction, pairing, a notification click, a live history change, or the
        window simply being raised) ends up with the same rebuild rather than each patching
        the list its own way. Preserves the current selection across the rebuild if the
        selected item is still present, since callers other than the original ones now
        trigger this far more often -- an item arriving should not silently drop whatever
        the user had selected to copy or save."""
        selected = self._list_box.get_selected_row()
        selected_id = selected.item_id if isinstance(selected, HistoryRow) else None
        while (child := self._list_box.get_first_child()) is not None:
            self._list_box.remove(child)
        self._rows.clear()
        for item in self._history.list_recent():
            row = HistoryRow(item)
            self._rows[item.id] = row
            self._list_box.append(row)
        if selected_id is not None and (restored := self._rows.get(selected_id)) is not None:
            self._list_box.select_row(restored)

    def notify_history_changed(self) -> None:
        """The application calls this whenever an item is added or expired, regardless of
        whether this window is currently open -- it is otherwise never told, and its list
        would then reflect only whatever was true the last time it happened to be shown.

        Reloads immediately if the window is visible, since that is exactly when someone
        could be looking at a now-stale list. A hidden window does nothing here: it is
        brought up to date the next time it is shown instead (`select_item` /
        `focus_send_and_select_newest`), so an item arriving while nobody is looking never
        pays for a rebuild that has no observer.
        """
        if self.get_visible():
            self._reload_history()

    def select_item(self, item_id: str) -> None:
        """Scroll to and select the row for `item_id`, refreshing first if not yet shown."""
        if item_id not in self._rows:
            self.refresh()
        row = self._rows.get(item_id)
        if row is not None:
            self._list_box.select_row(row)

    def focus_send_and_select_newest(self) -> None:
        """Ready the instant the window appears, whether raised by a shortcut or a
        notification with no particular item: the send field has focus, and the newest
        received item is selected, so shortcut-then-copy is a complete receive with no
        mouse.

        Reloads history first -- this is the path a shortcut or a plain reopen takes, and
        unlike `select_item` it has no specific item to check for absence, so a stale list
        would otherwise go unnoticed until something else happened to trigger a rebuild.
        """
        status = keyring.resolve_pairing_status(
            keyring.pairing_status(), history_has_items=self._history.has_any()
        )
        if status is not keyring.PairingStatus.PAIRED:
            return
        self._reload_history()
        self._entry.grab_focus()
        newest_row = self._list_box.get_row_at_index(0)
        if newest_row is not None:
            self._list_box.select_row(newest_row)
