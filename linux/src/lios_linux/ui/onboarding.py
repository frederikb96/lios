"""The first-run view: claim a fresh relay as its first device, or join one that already has
a device by pasting the pairing link it shows.

Shown instead of the history list until `lios_linux.keyring.is_paired()` is true. A relay
answers `POST /api/devices/bootstrap` with 403 the moment any device already exists, so
"claim" only ever works once per relay -- the fallback is always available and explained
rather than left as a dead end.

Untestable in this environment: needs a live display connection.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("GLib", "2.0")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from lios_linux.relaylink import pairing_flow  # noqa: E402
from lios_linux.relaylink.rest import RelayError  # noqa: E402

logger = logging.getLogger(__name__)


class OnboardingView:
    """Two ways in: claim an empty relay as its first device, or redeem a pairing link.

    A plain composing class rather than an `Adw.StatusPage` subclass -- `AdwStatusPage` is a
    final GType in libadwaita and PyGObject refuses to derive from it at runtime. `widget` is
    the `Adw.StatusPage` to place in the window's content area instead of inheriting from it.

    `on_paired(show_qr=...)` is called once pairing succeeds either way -- `show_qr=True`
    after claiming (this device is now the first, and the point of being first is showing the
    phone a code to scan), `show_qr=False` after joining (this device already has one to show
    for; there is nothing new to display).
    """

    def __init__(self, *, app: Any, on_paired: Callable[..., None]) -> None:
        self._app = app
        self._on_paired = on_paired

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
            width_request=320,
        )

        claim_button = Gtk.Button(
            label="Claim this relay (first device)", css_classes=["suggested-action", "pill"]
        )
        claim_button.connect("clicked", self._on_claim_clicked)
        box.append(claim_button)

        box.append(Gtk.Label(label="or", css_classes=["dim-label"]))

        self._uri_entry = Gtk.Entry(
            placeholder_text="Paste a pairing link from your other device"
        )
        box.append(self._uri_entry)

        join_button = Gtk.Button(label="Join with that link", css_classes=["pill"])
        join_button.connect("clicked", self._on_join_clicked)
        box.append(join_button)

        self._status_label = Gtk.Label(wrap=True, css_classes=["dim-label"])
        box.append(self._status_label)

        self.widget = Adw.StatusPage(
            icon_name="network-wireless-symbolic",
            title="Connect this device",
            description=f"Relay: {app.config.relay_url}",
            child=box,
        )

    def _on_claim_clicked(self, _button: Gtk.Button) -> None:
        self._status_label.set_label("Claiming the relay...")

        def worker() -> None:
            try:
                pairing_flow.start_first_device(
                    relay_url=self._app.config.relay_url, session=self._app.soup_session
                )
            except RelayError as exc:
                GLib.idle_add(self._on_claim_failed, str(exc))
                return
            GLib.idle_add(self._on_claimed)

        threading.Thread(target=worker, daemon=True).start()

    def _on_claim_failed(self, message: str) -> bool:
        logger.warning("bootstrap failed: %s", message)
        self._status_label.set_label(
            "This relay already has a device paired -- paste a pairing link from it above, "
            "instead of claiming it."
        )
        return bool(GLib.SOURCE_REMOVE)

    def _on_claimed(self) -> bool:
        self._on_paired(show_qr=True)
        return bool(GLib.SOURCE_REMOVE)

    def _on_join_clicked(self, _button: Gtk.Button) -> None:
        uri = self._uri_entry.get_text().strip()
        if not uri:
            return
        self._status_label.set_label("Joining...")

        def worker() -> None:
            try:
                pairing_flow.redeem_pairing_qr(uri=uri, session=self._app.soup_session)
            except Exception as exc:
                GLib.idle_add(self._on_join_failed, str(exc))
                return
            GLib.idle_add(self._on_joined)

        threading.Thread(target=worker, daemon=True).start()

    def _on_join_failed(self, message: str) -> bool:
        logger.warning("join failed: %s", message)
        self._status_label.set_label(f"Could not join: {message}")
        return bool(GLib.SOURCE_REMOVE)

    def _on_joined(self) -> bool:
        self._on_paired(show_qr=False)
        return bool(GLib.SOURCE_REMOVE)
