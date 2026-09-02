"""
Configuration loader for the LIOS relay.

Loading order (highest priority wins):
    1. config/config.yaml (complete defaults, always present)
    2. config-custom/config.override.yaml (sparse override, optional)
    3. LIOS_<SECTION>_<KEY> environment variable overrides
    4. ${VAR} placeholders anywhere in the merged config are resolved from the environment
       as a final pass

The merged result is validated by a pydantic model. Validation failure (missing field, wrong
type, unresolved placeholder) raises at startup -- there is no fallback default in code.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

#: The image places the relay's own checkout subtree at /app/relay (a sibling of
#: /app/protocol -- see docker/Dockerfile), so these are absolute rather than relative to
#: whatever the container's WORKDIR happens to be.
DEFAULT_CONFIG_PATH = Path("/app/relay/config/config.yaml")
OVERRIDE_CONFIG_PATH = Path("/app/relay/config-custom/config.override.yaml")

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(Exception):
    """Raised when configuration is missing, invalid, or unresolvable."""


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Recursively merge `override` into `base` in place. Override values win."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _apply_env_overrides(prefix: str, config: dict[str, Any]) -> None:
    """
    Apply LIOS_<SECTION>_<KEY> environment variable overrides to `config` in place.

    Only keys already present in the config are eligible -- this cannot introduce new keys.
    Nesting joins with underscores, e.g. `database.url` -> `LIOS_DATABASE_URL`.
    """
    for key, value in config.items():
        env_key = f"{prefix}_{key}".upper()

        if isinstance(value, dict):
            _apply_env_overrides(env_key, value)
            continue

        env_value = os.environ.get(env_key)
        if env_value is None:
            continue

        if isinstance(value, bool):
            config[key] = env_value.lower() in ("true", "1", "yes", "on")
        elif isinstance(value, int):
            try:
                config[key] = int(env_value)
            except ValueError as exc:
                raise ConfigError(
                    f"Environment override {env_key}={env_value!r} is not a valid int"
                ) from exc
        elif isinstance(value, list):
            config[key] = [item.strip() for item in env_value.split(",") if item.strip()]
        else:
            config[key] = env_value


def _resolve_placeholders(value: Any) -> Any:
    """Recursively resolve ${VAR} placeholders against the environment.

    An unset variable resolves to "" rather than raising -- some placeholders are
    legitimately optional (apns.*), and emptiness is validated per-field where it actually
    matters (DatabaseConfig.url) rather than blanket-enforced here.
    """
    if isinstance(value, dict):
        return {k: _resolve_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_placeholders(v) for v in value]
    if isinstance(value, str):
        def _sub(match: re.Match[str]) -> str:
            return os.environ.get(match.group(1), "")

        return _PLACEHOLDER_RE.sub(_sub, value)
    return value


def _resolve_config_path() -> Path:
    """Resolve the config.yaml path, checking an env override and a local checkout fallback."""
    env_path = os.environ.get("LIOS_CONFIG_PATH")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"Config not found at LIOS_CONFIG_PATH={env_path}")

    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH

    local_config = Path(__file__).parent.parent.parent.parent / "config" / "config.yaml"
    if local_config.exists():
        return local_config

    raise FileNotFoundError(f"Config not found at {DEFAULT_CONFIG_PATH} or {local_config}")


def _resolve_override_path() -> Path | None:
    """Resolve the sparse override path, checking an env var and a local checkout fallback."""
    env_path = os.environ.get("LIOS_CONFIG_OVERRIDE_PATH")
    if env_path:
        return Path(env_path)
    if OVERRIDE_CONFIG_PATH.exists():
        return OVERRIDE_CONFIG_PATH
    local_override = (
        Path(__file__).parent.parent.parent.parent / "config-custom" / "config.override.yaml"
    )
    return local_override if local_override.exists() else None


def _fix_db_url(url: str) -> str:
    """Ensure the async driver prefix: CNPG and most infra tooling generate `postgresql://`
    but the app needs `postgresql+asyncpg://`."""
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _load_raw_config() -> dict[str, Any]:
    """Load and merge the raw configuration dict from files and the environment."""
    config_path = _resolve_config_path()
    with open(config_path) as f:
        config: dict[str, Any] = yaml.safe_load(f) or {}

    override_path = _resolve_override_path()
    if override_path is not None:
        with open(override_path) as f:
            override: dict[str, Any] = yaml.safe_load(f) or {}
        _deep_merge(config, override)

    _apply_env_overrides("LIOS", config)

    return _resolve_placeholders(config)  # type: ignore[no-any-return]


_CONFIG: dict[str, Any] = {}


def _ensure_config() -> dict[str, Any]:
    """Ensure the raw config dict is loaded, return it."""
    global _CONFIG
    if not _CONFIG:
        _CONFIG = _load_raw_config()
    return _CONFIG


class ServerConfig(BaseModel):
    """HTTP server configuration."""

    host: str
    port: int
    log_level: str
    cors_origins: list[str] = Field(default_factory=list)


class DatabaseConfig(BaseModel):
    """Database connection configuration."""

    url: str
    pool_size: int
    max_overflow: int

    @field_validator("url")
    @classmethod
    def _url_must_be_set(cls, value: str) -> str:
        """Reject an empty database URL rather than defaulting it."""
        if not value:
            raise ValueError(
                "database.url resolved to an empty string -- set LIOS_DATABASE_URL or "
                "database.url in config.yaml"
            )
        return value


class ItemsConfig(BaseModel):
    """Limits on one item's sealed blob."""

    max_size_bytes: int


class RetentionConfig(BaseModel):
    """How long the relay holds an item before pruning it, regardless of ack state."""

    max_items: int
    max_age_days: int
    prune_interval_seconds: int


class PairingConfig(BaseModel):
    """Pairing-code lifetime."""

    code_ttl_seconds: int


class ApnsConfig(BaseModel):
    """APNs push configuration. Every field may be empty -- push is then simply disabled,
    never a startup failure, since a fresh deployment starts with no key configured."""

    key_id: str = ""
    team_id: str = ""
    topic: str = ""
    auth_key_b64: str = ""
    send_timeout_seconds: int = 10

    @property
    def configured(self) -> bool:
        """Whether every field push actually needs is present."""
        return bool(self.key_id and self.team_id and self.topic and self.auth_key_b64)


class RelayConfig(BaseModel):
    """The relay's full infrastructure configuration.

    Usage:
        config = get_config()
        print(config.server.port)
        print(config.database.url)
    """

    server: ServerConfig
    database: DatabaseConfig
    items: ItemsConfig
    retention: RetentionConfig
    pairing: PairingConfig
    apns: ApnsConfig


_config_instance: RelayConfig | None = None


def get_config() -> RelayConfig:
    """Get the global configuration instance, loading and validating it on first call.

    Raises:
        ConfigError: a required config value is missing or invalid.
    """
    global _config_instance
    if _config_instance is None:
        cfg = _ensure_config()

        database_cfg = dict(cfg.get("database") or {})
        db_url = database_cfg.get("url")
        if db_url:
            database_cfg["url"] = _fix_db_url(db_url)

        try:
            _config_instance = RelayConfig(
                server=ServerConfig(**(cfg.get("server") or {})),
                database=DatabaseConfig(**database_cfg),
                items=ItemsConfig(**(cfg.get("items") or {})),
                retention=RetentionConfig(**(cfg.get("retention") or {})),
                pairing=PairingConfig(**(cfg.get("pairing") or {})),
                apns=ApnsConfig(**(cfg.get("apns") or {})),
            )
        except ValidationError as exc:
            raise ConfigError(f"Invalid configuration: {exc}") from exc

    return _config_instance


def reset_config() -> None:
    """Reset the global configuration. Used by tests to load a fresh instance."""
    global _config_instance, _CONFIG
    _config_instance = None
    _CONFIG = {}
