"""Config load/save round-trip, and the corrupt-file fallback."""

from __future__ import annotations

from pathlib import Path

from lios_linux.config import DEFAULT_RELAY_URL, AppConfig


def test_defaults_when_file_does_not_exist(tmp_path: Path) -> None:
    config = AppConfig.load(tmp_path / "config.json")
    assert config.relay_url == DEFAULT_RELAY_URL
    assert config.max_items == 50
    assert config.max_age_days == 7


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    original = AppConfig(relay_url="https://relay.example.com", max_items=10, max_age_days=3)
    original.save(path)

    loaded = AppConfig.load(path)

    assert loaded == original


def test_corrupt_file_falls_back_to_defaults_rather_than_raising(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")

    config = AppConfig.load(path)

    assert config == AppConfig()


def test_unknown_fields_in_the_file_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"relay_url": "https://x", "from_a_future_version": true}', encoding="utf-8")

    config = AppConfig.load(path)

    assert config.relay_url == "https://x"
