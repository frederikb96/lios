"""Shown instead of onboarding when `keyring.pairing_status()` (as folded by
`keyring.resolve_pairing_status`) comes back `UNAVAILABLE` -- the Secret Service is
unreachable, its default collection is locked, or the device's own local history
contradicts a fresh "not paired" reading. None of those mean this device has never paired;
offering the onboarding view's "claim this relay as a first device" here would be destructive
on the strength of an error rather than a confirmed fact.

Untestable in this environment: needs a live display connection.
"""

from __future__ import annotations

import threading
from typing import Callable

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("GLib", "2.0")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from lios_linux import keyring  # noqa: E402


class KeyringUnavailableView:
    """One button: try to unlock the default keyring collection (which may show a system
    prompt) and re-check. `on_retry` is called on the main thread once that attempt finishes,
    whether or not it succeeded -- the caller re-runs its own status check either way, since
    that is the authoritative answer, not this view's guess about the unlock attempt.
    """

    def __init__(self, *, on_retry: Callable[[], None]) -> None:
        self._on_retry = on_retry

        button = Gtk.Button(label="Try again", css_classes=["suggested-action", "pill"])
        button.connect("clicked", self._on_retry_clicked)

        self.widget = Adw.StatusPage(
            icon_name="channel-secure-symbolic",
            title="Can't reach your credentials",
            description=(
                "LIOS could not read its stored pairing credential from your system "
                "keyring just now -- it may be locked, or the keyring service may not be "
                "running. This is not the same as never having paired. Unlock your "
                "keyring (a system prompt may already be open) and try again."
            ),
            child=button,
        )

    def _on_retry_clicked(self, _button: Gtk.Button) -> None:
        def worker() -> None:
            keyring.try_unlock_default_collection()
            GLib.idle_add(self._retry_on_main_thread)

        threading.Thread(target=worker, daemon=True).start()

    def _retry_on_main_thread(self) -> bool:
        self._on_retry()
        return bool(GLib.SOURCE_REMOVE)
