"""The resident application: one `Adw.Application` process, no daemon/UI split.

Ties every other module together: the relay connection (`relaylink`), the clipboard backend
(`clipboard.gdk`), local history (`history`), the portals (`portals`), and the CLI grammar
(`cli`). A `Gtk.Application` already provides, for free, everything a split daemon+UI design
would have to hand-build: single-instance enforcement, command-line forwarding from a second
invocation over D-Bus (`G_APPLICATION_HANDLES_COMMAND_LINE`), D-Bus activation from a desktop
file, and routing of notification/action clicks into `GAction`s.

`do_startup` runs once per process, before this invocation's own arguments are even parsed
(`do_command_line` always runs after it) -- so it does only what every invocation needs
regardless of what was asked: registering actions. Everything that commits the process to
staying alive -- `self.hold()`, opening the relay connection, the expiry timer, asking for
autostart permission -- waits for `_become_resident()`, called only by the commands that mean
to stick around (`show`, the windowless `background` used by autostart and the D-Bus service
file, and a `pair` that just succeeded). A plain parse error or `-h`/`--help` never reaches it,
so that invocation prints and exits instead of hanging forever with nothing left to do. The
window itself is created once and hidden (never destroyed) on close, so reopening it is
instant and its scroll position and selection survive.

Every network and clipboard call runs on a worker thread and hops back to the main loop via
`GLib.idle_add` before touching any GTK/history/config state -- none of those are thread-safe,
and the GTK main loop is the only place they may be touched from.

Untestable in a headless environment: needs a display, a session bus with the relevant
portals, and a Wayland session for the clipboard. Every module this file wires together is
unit-tested or explicitly flagged untestable on its own; this file is the integration, and
integration is exactly what has no coverage here.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Soup", "3.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Soup  # noqa: E402
from lios_protocol.wire import ItemSummary  # noqa: E402

from lios_linux import cli, keyring  # noqa: E402
from lios_linux.clipboard import gdk  # noqa: E402
from lios_linux.config import AppConfig  # noqa: E402
from lios_linux.history.models import Direction, HistoryItem, ItemKind  # noqa: E402
from lios_linux.history.store import HistoryStore  # noqa: E402
from lios_linux.portals import background, notifications  # noqa: E402
from lios_linux.relaylink import item_codec, pairing_flow, rest  # noqa: E402
from lios_linux.relaylink.item_codec import DecodedItem  # noqa: E402
from lios_linux.relaylink.stream import StreamConnection  # noqa: E402

if TYPE_CHECKING:
    from lios_linux.ui.window import LiosWindow

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


def _preview_for(kind: str, payload: bytes, *, filename: str | None) -> str:
    """A short display string -- the filename for image/file, a truncated decode for text."""
    if kind != "text":
        return filename or ""
    text = payload.decode("utf-8", errors="replace")
    return text if len(text) <= 80 else text[:77] + "..."


class LiosApplication(Adw.Application):
    """The one process; one window, created once and reused; resident once asked to be."""

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
        self._window: LiosWindow | None = None
        self._pending_item_id: str | None = None
        self._resident = False

    # -- Gio.Application lifecycle ---------------------------------------------------------

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._add_actions()

    def do_activate(self) -> None:
        self.show_window()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        argv = command_line.get_arguments()[1:]
        try:
            command = cli.parse(argv)
        except SystemExit as exc:
            return int(exc.code) if isinstance(exc.code, int) else 0
        self._dispatch(command)
        return 0

    # -- Wiring -------------------------------------------------------------------------------

    def _dispatch(self, command: cli.Command) -> None:
        if isinstance(command, cli.Pair):
            self._pair(command.uri)
        elif isinstance(command, cli.RunBackground):
            self._become_resident()
        else:
            self.show_window()

    def _become_resident(self) -> None:
        """Everything that commits this process to staying alive with no window required,
        run at most once regardless of how many resident-triggering invocations arrive.

        `self.hold()` is what actually keeps `Gtk.Application` from quitting once nothing
        else (a window, an in-flight D-Bus call) references it -- without it the process
        would exit the moment this invocation's `do_command_line` returns. The relay
        connection, the expiry timer and the autostart request all belong here rather than
        in `do_startup`, precisely so a `--help` or a failed `pair` never opens any of them.
        """
        if self._resident:
            return
        self._resident = True
        self.hold()
        self._history.expire(now=_now())
        GLib.timeout_add_seconds(_EXPIRY_INTERVAL_SECONDS, self._on_expiry_timer)
        self._connect_to_relay_if_paired()
        self._request_autostart_if_not_yet_asked()

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
            get_catch_up_since=self._catch_up_since,
        )
        self._stream.start()

    def _catch_up_since(self) -> datetime:
        """The watermark the next catch-up resumes from: the newest relay timestamp among
        items this device has already received, or "now" if it has never received anything
        -- a fresh pairing should not retroactively pull the fleet's whole retained history,
        only whatever arrives from here on."""
        return self._history.get_catch_up_since() or _now()

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
            command=["lios", "background"],
            on_response=on_response,
        )

    def _on_expiry_timer(self) -> bool:
        self._history.expire(now=_now())
        return bool(GLib.SOURCE_CONTINUE)

    # -- Sending ------------------------------------------------------------------------------

    def send_file(self, path: str) -> None:
        """Upload the file at `path` -- called by the window's paste, drop and file-picker
        handlers, each of which already knows a concrete path."""

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
        """Called from `StreamConnection`, already on the main loop -- fetch off a worker.

        Skips outright if `item.id` is already in local history: the live stream and a
        catch-up can genuinely announce the same item twice in one reconnect (a catch-up
        spanning the moment the socket opens can list something the stream is about to
        announce anyway), and a widened catch-up window can also echo back an item this
        very device sent, since the relay's catch-up list carries no per-device filtering at
        all. Either way it is already handled -- checked here, on the main loop, rather than
        in the worker below, matching the rule that only the main loop touches history state.
        """
        if self._history.get(str(item.id)) is not None:
            return
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
        GLib.idle_add(self._on_item_decoded, str(item.id), item.created_at, decoded)

    def _on_item_decoded(
        self, item_id: str, relay_created_at: datetime, decoded: DecodedItem
    ) -> bool:
        """Store the item and notify -- and advance the catch-up watermark regardless of
        whether this call turns out to be a duplicate (`_on_item_announced`'s guard is not
        airtight on its own: two fetches for the same id can both be in flight on their
        worker threads before either reaches here). Advancing is always correct even then,
        since it only ever moves forward to a timestamp this device has genuinely now seen.
        """
        self._history.advance_catch_up_since(relay_created_at)
        if self._history.get(item_id) is not None:
            return bool(GLib.SOURCE_REMOVE)
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
        notification = notifications.build_item_arrived_notification(
            item_id, kind=decoded.kind, filename=decoded.filename
        )
        self.send_notification(item_id, notification)
        return bool(GLib.SOURCE_REMOVE)

    # -- Notification / action handlers -------------------------------------------------------

    def _on_copy_item(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        """Copy button or its accelerator, inside the window -- never a file item, which
        offers Save instead (see `ui.history_row.HistoryRow.supports_copy`)."""
        item_id = parameter.get_string()
        item = self._history.get(item_id)
        if item is None or item.kind == ItemKind.FILE:
            return
        blob_path = self._history.blob_path(item_id)
        if blob_path is None:
            return

        def worker() -> None:
            data = blob_path.read_bytes()
            GLib.idle_add(self._write_clipboard, item.kind, data)

        threading.Thread(target=worker, daemon=True).start()

    def _write_clipboard(self, kind: ItemKind, data: bytes) -> bool:
        if kind == ItemKind.IMAGE:
            gdk.write_image_png(data)
        else:
            gdk.write_text(data.decode("utf-8", errors="replace"))
        return bool(GLib.SOURCE_REMOVE)

    def _on_open_item(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        """A notification's default action -- every kind, always: opening the window is what
        makes the Copy/Save that follows a genuine in-window input event."""
        item_id = parameter.get_string()
        notifications.withdraw(self, item_id)
        self._pending_item_id = item_id
        self.show_window()

    def _on_save_item(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        item_id = parameter.get_string()
        blob_path = self._history.blob_path(item_id)
        item = self._history.get(item_id)
        if blob_path is None or item is None:
            return
        # `None` if XDG user dirs are unconfigured -- falls back to ~/Downloads rather than
        # failing the save outright.
        downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        downloads_dir = Path(downloads) if downloads else Path.home() / "Downloads"
        target = downloads_dir / (item.filename or f"{item_id}.bin")
        target.write_bytes(blob_path.read_bytes())

    # -- Pairing ------------------------------------------------------------------------------

    def _pair(self, uri: str | None) -> None:
        if uri is None:
            self.show_window()
            return
        try:
            pairing_flow.redeem_pairing_qr(uri=uri, session=self.soup_session)
        except Exception:
            logger.exception("pairing failed")
            return
        self.on_paired()

    def on_paired(self) -> None:
        """Called once this device has a device token and group key, however it got them --
        the onboarding view (claim or join) and the `pair` CLI/action both funnel here.

        `_become_resident()` covers a standalone `lios pair <uri>` invocation that had no
        window and was not otherwise resident yet -- pairing successfully is exactly the
        moment it should start behaving like every other resident invocation, rather than
        connecting to the relay and then immediately exiting with nothing left to hold it
        open. The explicit `_connect_to_relay_if_paired()` call underneath still matters on
        its own even when already resident (e.g. pairing from the onboarding view): the
        earlier residency-establishing call ran before a token existed, so its own attempt to
        connect was a no-op.
        """
        self._become_resident()
        self._connect_to_relay_if_paired()

    # -- Window ------------------------------------------------------------------------------

    def show_window(self) -> None:
        """Raise the window, creating it once on first use and reusing it afterwards.

        With no pending item from a notification click, the window itself decides what "ready"
        means -- focusing the send field and selecting the newest received item.
        """
        self._become_resident()
        if self._window is None:
            from lios_linux.ui.window import LiosWindow

            self._window = LiosWindow(application=self, history=self._history)
            self._window.connect("close-request", self._on_window_close_request)
        if self._pending_item_id is not None:
            self._window.select_item(self._pending_item_id)
            self._pending_item_id = None
        else:
            self._window.focus_send_and_select_newest()
        self._window.present()

    def _on_window_close_request(self, window: Gtk.ApplicationWindow) -> bool:
        """Hide rather than destroy -- the process stays resident (`_become_resident()`
        already held it, since showing a window always goes through there first), and
        reopening the same window is instant with its scroll position and selection intact."""
        window.set_visible(False)
        return bool(Gdk.EVENT_STOP)

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
