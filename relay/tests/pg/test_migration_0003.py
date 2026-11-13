"""`pg` test for the push-ticket migration, against a database that already holds devices."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from lios_relay.config import reset_config

_RELAY_ROOT = Path(__file__).parent.parent.parent


def _alembic(database_url: str, action: str, revision: str) -> None:
    os.environ["LIOS_DATABASE_URL"] = database_url
    reset_config()
    cfg = Config(str(_RELAY_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_RELAY_ROOT / "alembic"))
    getattr(command, action)(cfg, revision)


async def test_raw_tokens_are_dropped_and_devices_survive(postgres_url: str) -> None:
    await asyncio.to_thread(_alembic, postgres_url, "downgrade", "0002")
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE devices CASCADE"))
            await conn.execute(
                text(
                    "INSERT INTO devices (display_name, platform, token_hash, apns_token) "
                    "VALUES ('Phone', 'ios', 'hash', 'deadbeef')"
                )
            )

        await asyncio.to_thread(_alembic, postgres_url, "upgrade", "head")

        async with engine.connect() as conn:
            columns = {
                row[0]
                for row in await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'devices'"
                    )
                )
            }
            row = (await conn.execute(text("SELECT display_name, push_ticket FROM devices"))).one()
    finally:
        await engine.dispose()

    assert "apns_token" not in columns
    assert tuple(row) == ("Phone", None)
