"""Static application configuration, loaded from a JSON file under the Flatpak's own data dir.

Config vs settings: everything here is user-editable through `AdwPreferencesDialog` and
persisted back to the same file -- there is no separate database for it. Not secret: the relay
URL and retention numbers carry no credential. The device token and group key are secrets and
live in the Secret Service instead (see `lios_linux.keyring`), never in this file.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

#: How many of the newest items `HistoryStore.expire` keeps -- spec row 57's default.
DEFAULT_MAX_ITEMS = 50

#: How many days an item survives regardless of the item cap -- spec row 57's default.
DEFAULT_MAX_AGE_DAYS = 7

#: The relay Freddy runs. Shipped as the default so there is nothing to type on a fresh
#: install -- editable in preferences for anyone self-hosting their own.
DEFAULT_RELAY_URL = "https://lios.frederikberg.net"


@dataclass
class AppConfig:
    """Everything the preferences dialog edits."""

    relay_url: str = DEFAULT_RELAY_URL
    max_items: int = DEFAULT_MAX_ITEMS
    max_age_days: int = DEFAULT_MAX_AGE_DAYS
    autostart_requested: bool = False

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        """Read the config file, or return all-defaults if it does not exist yet.

        A corrupt file is treated the same as a missing one -- falling back to defaults rather
        than crashing the app on startup over a config the user can fix through the
        preferences dialog, which will overwrite it on first save.
        """
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known_fields = {field for field in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in known_fields})

    def save(self, path: Path) -> None:
        """Write this config to `path`, creating parent directories if needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
