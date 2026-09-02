"""Config loading: defaults, env overrides, and the fail-fast database.url guard."""

from __future__ import annotations

import pytest

from lios_relay.config import ConfigError, get_config, reset_config


@pytest.fixture(autouse=True)
def _reset_config_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets a fresh config instance and a clean set of LIOS_* env vars."""
    reset_config()
    for key in list(__import__("os").environ):
        if key.startswith("LIOS_"):
            monkeypatch.delenv(key, raising=False)
    yield
    reset_config()


def test_get_config_fails_fast_without_database_url() -> None:
    with pytest.raises(ConfigError, match="database.url"):
        get_config()


def test_get_config_loads_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIOS_DATABASE_URL", "postgresql://user:pass@localhost/lios")
    config = get_config()

    assert config.server.port == 8080
    assert config.items.max_size_bytes == 26214400
    assert config.retention.max_items == 50
    assert config.retention.max_age_days == 7
    assert config.pairing.code_ttl_seconds == 600


def test_database_url_gains_asyncpg_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIOS_DATABASE_URL", "postgresql://user:pass@localhost/lios")
    config = get_config()
    assert config.database.url.startswith("postgresql+asyncpg://")


def test_env_override_wins_over_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIOS_DATABASE_URL", "postgresql://user:pass@localhost/lios")
    monkeypatch.setenv("LIOS_SERVER_PORT", "9999")
    monkeypatch.setenv("LIOS_RETENTION_MAX_ITEMS", "5")
    config = get_config()

    assert config.server.port == 9999
    assert config.retention.max_items == 5


def test_apns_is_unconfigured_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIOS_DATABASE_URL", "postgresql://user:pass@localhost/lios")
    config = get_config()
    assert config.apns.configured is False


def test_apns_is_configured_once_every_field_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIOS_DATABASE_URL", "postgresql://user:pass@localhost/lios")
    monkeypatch.setenv("LIOS_APNS_KEY_ID", "KEY123")
    monkeypatch.setenv("LIOS_APNS_TEAM_ID", "TEAM123")
    monkeypatch.setenv("LIOS_APNS_AUTH_KEY_B64", "c29tZWtleQ==")
    config = get_config()
    assert config.apns.configured is True
