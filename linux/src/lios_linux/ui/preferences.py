"""`AdwPreferencesDialog`: relay URL, retention, and where the raise-window shortcut gets bound.

Untestable in this environment: needs a live display connection.
"""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw  # noqa: E402


class LiosPreferencesDialog(Adw.PreferencesDialog):
    """Edits `app.config` directly, saving through `app.save_config()` on every change."""

    def __init__(self, *, app: Any) -> None:
        super().__init__()
        self._app = app
        config = app.config

        page = Adw.PreferencesPage()
        self.add(page)

        connection_group = Adw.PreferencesGroup(title="Connection")
        page.add(connection_group)
        relay_row = Adw.EntryRow(title="Relay URL")
        relay_row.set_text(config.relay_url)
        relay_row.connect("changed", self._on_relay_url_changed)
        connection_group.add(relay_row)

        retention_group = Adw.PreferencesGroup(title="History")
        page.add(retention_group)

        items_row = Adw.SpinRow.new_with_range(1, 500, 1)
        items_row.set_title("Items kept")
        items_row.set_value(config.max_items)
        items_row.connect("notify::value", self._on_max_items_changed)
        retention_group.add(items_row)

        days_row = Adw.SpinRow.new_with_range(1, 90, 1)
        days_row.set_title("Days kept")
        days_row.set_value(config.max_age_days)
        days_row.connect("notify::value", self._on_max_age_days_changed)
        retention_group.add(days_row)

        page.add(
            Adw.PreferencesGroup(
                title="Shortcut",
                description=(
                    "Bind a key in GNOME Settings (or any desktop's own keyboard settings) "
                    "to `flatpak run --command=lios io.github.frederikb96.Lios show` to "
                    "raise this window, focused and ready to paste."
                ),
            )
        )

    def _on_relay_url_changed(self, entry_row: Adw.EntryRow) -> None:
        self._app.config.relay_url = entry_row.get_text()
        self._app.save_config()

    def _on_max_items_changed(self, spin_row: Adw.SpinRow, _pspec: object) -> None:
        self._app.config.max_items = int(spin_row.get_value())
        self._app.save_config()

    def _on_max_age_days_changed(self, spin_row: Adw.SpinRow, _pspec: object) -> None:
        self._app.config.max_age_days = int(spin_row.get_value())
        self._app.save_config()
