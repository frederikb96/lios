"""Background pruning: the relay never becomes an archive.

Runs on a timer for the lifetime of the process (started and stopped from `server.py`'s
lifespan). Every pass prunes, in order: items past `retention.max_age_days` regardless of ack
state, items beyond `retention.max_items` (oldest first, keeping the newest), items every
snapshotted recipient has acked, and pairing sessions past their expiry.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from lios_relay.config import RetentionConfig
from lios_relay.database.connection import DatabaseConnection
from lios_relay.database.models import Item, ItemAck, ItemRecipient
from lios_relay.database.repository import prune_expired_pairing_sessions

logger = logging.getLogger(__name__)


async def _prune_aged_out(session: AsyncSession, max_age_days: int) -> int:
    """Delete every item older than `max_age_days`, whatever its ack state."""
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    result = await session.execute(delete(Item).where(Item.created_at < cutoff))
    return cast(CursorResult, result).rowcount or 0


async def _prune_beyond_count(session: AsyncSession, max_items: int) -> int:
    """Keep only the newest `max_items` items, oldest-first beyond that deleted."""
    total = await session.scalar(select(func.count()).select_from(Item))
    if total is None or total <= max_items:
        return 0
    overflow = total - max_items
    stale_ids = (
        await session.execute(
            select(Item.id).order_by(Item.created_at.asc()).limit(overflow)
        )
    ).scalars().all()
    if not stale_ids:
        return 0
    result = await session.execute(delete(Item).where(Item.id.in_(stale_ids)))
    return cast(CursorResult, result).rowcount or 0


async def _prune_fully_acked(session: AsyncSession) -> int:
    """Delete every item whose full `ItemRecipient` snapshot has a matching `ItemAck`.

    An item created with an empty recipient snapshot (the sender was the only paired device
    at the time) is vacuously fully acked and would be deleted on the very next pass --
    correct: nobody was ever waiting on it.
    """
    has_ack = select(ItemAck.item_id).where(
        ItemAck.item_id == ItemRecipient.item_id,
        ItemAck.device_id == ItemRecipient.device_id,
    )
    unacked_item_ids = select(ItemRecipient.item_id).where(~has_ack.exists())
    result = await session.execute(delete(Item).where(~Item.id.in_(unacked_item_ids)))
    return cast(CursorResult, result).rowcount or 0


async def run_prune_pass(db: DatabaseConnection, config: RetentionConfig) -> None:
    """Run one full prune pass in a single transaction."""
    async with db.session() as session:
        aged = await _prune_aged_out(session, config.max_age_days)
        overflow = await _prune_beyond_count(session, config.max_items)
        acked = await _prune_fully_acked(session)
        sessions_expired = await prune_expired_pairing_sessions(session)

    if aged or overflow or acked or sessions_expired:
        logger.info(
            "retention prune: %d aged out, %d beyond count, %d fully acked, "
            "%d expired pairing sessions",
            aged, overflow, acked, sessions_expired,
        )


class RetentionTask:
    """Runs :func:`run_prune_pass` on a fixed interval until stopped."""

    def __init__(self, db: DatabaseConnection, config: RetentionConfig) -> None:
        self._db = db
        self._config = config
        self._task: asyncio.Task[None] | None = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._config.prune_interval_seconds)
            try:
                await run_prune_pass(self._db, self._config)
            except Exception:
                logger.exception("retention prune pass failed; will retry next interval")

    async def start(self) -> None:
        """Start the background loop. A no-op if already running."""
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the background loop and wait for it to exit."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
