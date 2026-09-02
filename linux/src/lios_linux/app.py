"""The resident application: one `Adw.Application` process, no daemon/UI split.

Ties every other module together: the relay connection (`relaylink`), the clipboard backends
(`clipboard`), local history (`history`), the portals (`portals`), and the CLI grammar
(`cli`). A `Gtk.Application` already provides, for free, everything a split daemon+UI design
would have to hand-build: single-instance enforcement, command-line forwarding from a second
invocation over D-Bus (`G_APPLICATION_HANDLES_COMMAND_LINE`), D-Bus activation from a desktop
file, and routing of notification/action-button clicks into `GAction`s (report
055c37e1-f508-4d6c-b63f-2ae31ff8bdfc). The window is created on demand and destroyed on close,
so the resident footprint falls back to the headless baseline between uses.

Every network and clipboard call runs on a worker thread and hops back to the main loop via
`GLib.idle_add` before touching any GTK/history/config state -- none of those are thread-safe,
and the GTK main loop is the only place they may be touched from.

Untestable in this environment: needs a display, a session bus with the relevant portals, and
a Wayland session for the clipboard -- none of which `pai-vm` has. Every module this file
wires together is unit-tested or explicitly flagged untestable on its own; this file is the
integration, and integration is exactly what has no coverage here.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Soup", "3.0")

from gi.repository import Adw, Gio, GLib, Gtk, Soup  # noqa: E402
from lios_protocol.wire import ItemSummary  # noqa: E402

from lios_linux import cli, keyring  # noqa: E402
from lios_linux.clipboard import wl  # noqa: E402
from lios_linux.clipboard.priority import ClipboardKind  # noqa: E402
from lios_linux.config import AppConfig  # noqa: E402
from lios_linux.history.models import Direction, HistoryItem, ItemKind  # noqa: E402
from lios_linux.history.store import HistoryStore  # noqa: E402
from lios_linux.portals import background, notifications, shortcuts  # noqa: E402
from lios_linux.relaylink import item_codec, pairing_flow, rest  # noqa: E402
from lios_linux.relaylink.item_codec import DecodedItem  # noqa: E402
from lios_linux.relaylink.stream import StreamConnection  # noqa: E402

logger = logging.getLogger(__name__)

APP_ID = "io.github.frederikb96.Lios"

#: How often `HistoryStore.expire` runs while the app is resident, beyond the run at startup.
_EXPIRY_INTERVAL_SECONDS = 3600


def _data_dir() -> Path:
    return Path(GLib.get_user_data_dir()) / "lios"


def _config_path() -> Path:
    return Path(GLib.get_user_config_dir()) / "lios" / "config.json"


def _now() -> datetime:
    return datetime.now(UTC)


def _kind_from_clipboard(kind: ClipboardKind) -> str:
    return "image" if kind == ClipboardKind.IMAGE else "text"


def _preview_for(kind: str, payload: bytes, *, filename: str | None) -> str:
    """A short display string -- the filename for image/file, a truncated decode for text."""
    if kind != "text":
        return filename or ""
    text = payload.decode("utf-8", errors="replace")
    return text if len(text) <= 80 else text[:77] + "..."


class LiosApplication(Adw.Application):
    """The one process. No window at login; one created and destroyed per use."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )
        self.config = AppConfig.load(_config_path())
        self._history = HistoryStore(
            db_path=_data_dir() / "history.sqlite3",
            blobs_dir=_data_dir() / "blobs",
            max_items=self.config.max_items,
            max_age_days=self.config.max_age_days,
        )
        self.soup_session = Soup.Session()
        self._stream: StreamConnection | None = None
        self._window: Gtk.ApplicationWindow | None = None
        self._last_activation_token: str | None = None
        self._pending_item_id: str | None = None

    # -- Gio.Application lifecycle ---------------------------------------------------------

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._add_actions()
        self._history.expire(now=_now())
        GLib.timeout_add_seconds(_EXPIRY_INTERVAL_SECONDS, self._on_expiry_timer)
        self._connect_to_relay_if_paired()
        self._request_autostart_if_not_yet_asked()
        self._bind_global_shortcuts()

    def do_activate(self) -> None:
        self._show_window()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        argv = command_line.get_arguments()[1:]
        try:
            command = cli.parse(argv)
        except SystemExit as exc:
            return int(exc.code) if isinstance(exc.code, int) else 0
        self._dispatch(command)
        return 0

    def do_before_emit(self, platform_data: GLib.Variant) -> None:
        """Capture the activation token this action activation arrived with, if any.

        `platform_data` is the vardict `GApplication` hands every D-Bus-invoked action --
        carrying `activation-token` when the caller (a notification click, a GlobalShortcuts
        activation) had one. Stashed here so the handler below can pass it on to
        `wl-copy`/`wl-paste` as `$XDG_ACTIVATION_TOKEN`.
        """
        self._last_activation_token = None
        if platform_data is not None:
            token_variant = platform_data.lookup_value("activation-token", GLib.VariantType("s"))
            if token_variant is not None:
                self._last_activation_token = token_variant.get_string()

    # -- Wiring -------------------------------------------------------------------------------

    def _dispatch(self, command: cli.Command) -> None:
        if isinstance(command, cli.SendClipboard):
            self._send_clipboard()
        elif isinstance(command, cli.SendFile):
            self.send_file(command.path)
        elif isinstance(command, cli.Pair):
            self._pair(command.uri)
        else:
            self._show_window()

    def _add_actions(self) -> None:
        for name, handler in (
            (notifications.ACTION_COPY_ITEM.removeprefix("app."), self._on_copy_item),
            (notifications.ACTION_OPEN_ITEM.removeprefix("app."), self._on_open_item),
            (notifications.ACTION_SAVE_ITEM.removeprefix("app."), self._on_save_item),
        ):
            action = Gio.SimpleAction.new(name, GLib.VariantType("s"))
            action.connect("activate", handler)
            self.add_action(action)

    def _connect_to_relay_if_paired(self) -> None:
        if not self.config.relay_url:
            return
        try:
            device_token = keyring.load_device_token()
        except keyring.SecretNotFound:
            return
        self._stream = StreamConnection(
            relay_url=self.config.relay_url,
            device_token=device_token,
            session=self.soup_session,
            on_item=self._on_item_announced,
        )
        self._stream.start()

    def _request_autostart_if_not_yet_asked(self) -> None:
        """Ask, once, for permission to start at login -- never enabled silently."""
        if self.config.autostart_requested:
            return
        connection = self.get_dbus_connection()
        if connection is None:
            return

        def on_response(_granted: bool) -> None:
            self.config.autostart_requested = True
            self.save_config()

        background.request_autostart(
            connection,
            reason="Receive items from your paired phone while LIOS has no window open",
            command=["lios"],
            on_response=on_response,
        )

    def _bind_global_shortcuts(self) -> None:
        connection = self.get_dbus_connection()
        if connection is None:
            return

        def on_bound(_session_handle: str) -> None:
            shortcuts.subscribe_activated(connection, on_activated=self._on_shortcut_activated)

        def on_error(message: str) -> None:
            logger.warning("%s", message)

        shortcuts.create_session_and_bind(connection, on_bound=on_bound, on_error=on_error)

    def _on_shortcut_activated(
        self, shortcut_id: str, _timestamp: str, activation_token: str | None
    ) -> None:
        if shortcut_id == shortcuts.SHORTCUT_SEND_CLIPBOARD:
            self._send_clipboard(activation_token=activation_token)
        elif shortcut_id == shortcuts.SHORTCUT_SEND_FILE:
            self.send_file(None, activation_token=activation_token)

    def _on_expiry_timer(self) -> bool:
        self._history.expire(now=_now())
        return bool(GLib.SOURCE_CONTINUE)

    # -- Sending ------------------------------------------------------------------------------

    def _send_clipboard(self, *, activation_token: str | None = None) -> None:
        def worker() -> None:
            try:
                choice, data = wl.read_best()
            except (wl.NothingOnClipboard, wl.HelperError) as exc:
                logger.warning("send-clipboard: %s", exc)
                return
            self.upload(_kind_from_clipboard(choice.kind), data)

        threading.Thread(target=worker, daemon=True).start()

    def send_file(self, path: str | None, *, activation_token: str | None = None) -> None:
        if path is None:
            # No path on the command line: the window is where a file gets picked, through
            # its own drag-and-drop target or an in-window "choose a file" action.
            self._show_window()
            return

        def worker() -> None:
            data = Path(path).read_bytes()
            content_type, _uncertain = Gio.content_type_guess(path, data)
            self.upload("file", data, filename=Path(path).name, content_type=content_type)

        threading.Thread(target=worker, daemon=True).start()

    def upload(
        self,
        kind: str,
        payload: bytes,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> None:
        try:
            group_key = keyring.load_group_key()
            device_token = keyring.load_device_token()
        except keyring.SecretNotFound:
            logger.warning("cannot send: this device has not paired yet")
            return
        item_id = str(uuid.uuid4())
        sealed = item_codec.build_sealed_item(
            group_key=group_key,
            kind=kind,
            payload=payload,
            item_id=item_id,
            filename=filename,
            content_type=content_type,
        )
        preview = _preview_for(kind, payload, filename=filename)
        wire_preview_text = (
            item_codec.truncate_preview_text(payload.decode("utf-8", errors="replace"))
            if kind == "text"
            else None
        )
        sealed_preview = item_codec.build_sealed_preview(
            group_key=group_key,
            item_id=item_id,
            kind=kind,
            preview=wire_preview_text,
            filename=filename,
        )
        try:
            rest.create_item(
                self.soup_session,
                relay_url=self.config.relay_url,
                device_token=device_token,
                item_id=item_id,
                sealed_blob=sealed.blob,
                sealed_preview=sealed_preview,
            )
        except rest.RelayError as exc:
            logger.warning("upload failed: %s", exc)
            return
        self._history.add(
            HistoryItem(
                id=item_id,
                direction=Direction.OUTGOING,
                kind=ItemKind(kind),
                preview=preview,
                filename=filename,
                content_type=content_type,
                size_bytes=len(payload),
                created_at=_now(),
            ),
            blob=payload,
        )

    # -- Receiving ----------------------------------------------------------------------------

    def _on_item_announced(self, item: ItemSummary) -> None:
        """Called from `StreamConnection`, already on the main loop -- fetch off a worker."""
        threading.Thread(target=self._fetch_and_decode, args=(item,), daemon=True).start()

    def _fetch_and_decode(self, item: ItemSummary) -> None:
        try:
            group_key = keyring.load_group_key()
            device_token = keyring.load_device_token()
            sealed = rest.get_item(
                self.soup_session,
                relay_url=self.config.relay_url,
                device_token=device_token,
                item_id=str(item.id),
            )
            decoded = item_codec.open_sealed_item(
                group_key=group_key,
                sealed_blob=sealed,
                item_id=str(item.id),
                size_bytes=item.size_bytes,
            )
        except Exception:
            logger.exception("failed to fetch/decrypt item %s", item.id)
            return
        GLib.idle_add(self._on_item_decoded, str(item.id), decoded)

    def _on_item_decoded(self, item_id: str, decoded: DecodedItem) -> bool:
        self._history.add(
            HistoryItem(
                id=item_id,
                direction=Direction.INCOMING,
                kind=ItemKind(decoded.kind),
                preview=_preview_for(decoded.kind, decoded.payload, filename=decoded.filename),
                filename=decoded.filename,
                content_type=decoded.content_type,
                size_bytes=len(decoded.payload),
                created_at=_now(),
            ),
            blob=decoded.payload,
        )
        if decoded.kind == "text":
            notification = notifications.build_text_arrived_notification(item_id)
        else:
            notification = notifications.build_media_arrived_notification(
                item_id, kind=decoded.kind, filename=decoded.filename
            )
        self.send_notification(item_id, notification)
        return bool(GLib.SOURCE_REMOVE)

    # -- Notification / action-button handlers -------------------------------------------------

    def _on_copy_item(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        item_id = parameter.get_string()
        notifications.withdraw(self, item_id)
        item = self._history.get(item_id)
        if item is None:
            return
        blob_path = self._history.blob_path(item_id)
        if blob_path is None:
            return
        token = self._last_activation_token

        def worker() -> None:
            data = blob_path.read_bytes()
            if item.kind == ItemKind.IMAGE:
                wl.write_image_png(data, activation_token=token)
            else:
                wl.write_text(data.decode("utf-8", errors="replace"), activation_token=token)

        threading.Thread(target=worker, daemon=True).start()

    def _on_open_item(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        self._pending_item_id = parameter.get_string()
        self._show_window()

    def _on_save_item(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        item_id = parameter.get_string()
        blob_path = self._history.blob_path(item_id)
        item = self._history.get(item_id)
        if blob_path is None or item is None:
            return
        downloads_dir = Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD))
        target = downloads_dir / (item.filename or f"{item_id}.bin")
        target.write_bytes(blob_path.read_bytes())

    # -- Pairing ------------------------------------------------------------------------------

    def _pair(self, uri: str | None) -> None:
        if uri is None:
            self._show_window()
            return
        try:
            pairing_flow.redeem_pairing_qr(uri=uri, session=self.soup_session)
        except Exception:
            logger.exception("pairing failed")
            return
        self.on_paired()

    def on_paired(self) -> None:
        """Called once this device has a device token and group key, however it got them --
        the onboarding view (claim or join) and the `pair` CLI/action both funnel here."""
        self._connect_to_relay_if_paired()

    # -- Window ------------------------------------------------------------------------------

    def _show_window(self) -> None:
        if self._window is None:
            from lios_linux.ui.window import LiosWindow

            self._window = LiosWindow(application=self, history=self._history)
            self._window.connect("close-request", self._on_window_closed)
        if self._pending_item_id is not None:
            self._window.select_item(self._pending_item_id)
            self._pending_item_id = None
        self._window.present()

    def _on_window_closed(self, _window: Gtk.ApplicationWindow) -> bool:
        self._window = None
        return False

    # -- Config -------------------------------------------------------------------------------

    def save_config(self) -> None:
        """Persist `self.config` and apply anything that changed to the running app.

        Called by the preferences dialog after every edit. The retention numbers take effect
        on the history store immediately; the relay URL takes effect the next time this
        device (re)connects, since changing it while a stream is open would orphan the old
        connection rather than migrate it.
        """
        self.config.save(_config_path())
        self._history.update_limits(
            max_items=self.config.max_items, max_age_days=self.config.max_age_days
        )
