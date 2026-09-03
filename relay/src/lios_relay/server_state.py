"""Process-global state the API routers depend on: a DB session per request, and the
in-process broadcaster that turns a new item into a stream event for every connected
WebSocket client the item is addressed to.

Kept separate from `server.py` so routers can depend on it without importing the app
factory, which imports the routers -- avoiding the circular import that would otherwise
create.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Collection

from sqlalchemy.ext.asyncio import AsyncSession

from lios_relay.database.connection import get_db_connection

logger = logging.getLogger(__name__)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, from the global DatabaseConnection."""
    db = get_db_connection()
    async with db.session() as session:
        yield session


class ItemBroadcaster:
    """Fans out a new item's summary to every currently connected `/api/stream` socket whose
    device is one of that item's intended recipients.

    Each connected client gets its own bounded `asyncio.Queue`, keyed by the device id its
    connection authenticated as -- `publish` consults that key so a sender is never announced
    the item it just uploaded, and a targeted item reaches only the device it targets. Never
    blocks on a slow or stuck client -- a full queue is dropped from rather than awaited, since
    a client that fell behind should reconnect and catch up through `GET /api/items?since=`
    rather than have its backlog delay every other client's delivery.
    """

    def __init__(self) -> None:
        self._queues: dict[asyncio.Queue[str], uuid.UUID] = {}

    def subscribe(self, device_id: uuid.UUID) -> asyncio.Queue[str]:
        """Register a new connection authenticated as `device_id`, returning the queue it
        should read from."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
        self._queues[queue] = device_id
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        """Deregister a connection that is closing."""
        self._queues.pop(queue, None)

    def publish(self, event_json: str, recipient_ids: Collection[uuid.UUID]) -> None:
        """Hand `event_json` to every currently connected client among `recipient_ids`."""
        recipients = set(recipient_ids)
        for queue, device_id in self._queues.items():
            if device_id not in recipients:
                continue
            try:
                queue.put_nowait(event_json)
            except asyncio.QueueFull:
                logger.warning("dropped a stream event for a slow client")


_broadcaster: ItemBroadcaster | None = None


def get_broadcaster() -> ItemBroadcaster:
    """The process-global broadcaster, created on first use."""
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = ItemBroadcaster()
    return _broadcaster


def reset_broadcaster() -> None:
    """Reset the global broadcaster. Used by tests to isolate subscriptions per test."""
    global _broadcaster
    _broadcaster = None
