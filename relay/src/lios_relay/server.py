"""LIOS relay ASGI server.

Deliberately dumb: it stores ciphertext it cannot open, tracks which device has taken which
item, expires everything on the retention policy, and rings an APNs doorbell when the
recipient is an iOS device. It makes no decisions about content because it cannot see any --
there is no auth layer of the oauth2-proxy/ForwardAuth kind either; every device carries its
own bearer token, checked per request by `lios_relay.auth`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from lios_relay.api import all_routers
from lios_relay.config import get_config
from lios_relay.database import close_database, init_database
from lios_relay.retention import RetentionTask
from lios_relay.server_state import reset_broadcaster

logger = logging.getLogger(__name__)

_retention_task: RetentionTask | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize the database and start the retention loop; reverse both on shutdown."""
    global _retention_task

    config = get_config()
    logging.basicConfig(level=config.server.log_level)
    logger.info("LIOS relay starting")

    db = await init_database(config.database)
    reset_broadcaster()

    _retention_task = RetentionTask(db, config.retention)
    await _retention_task.start()
    logger.info("retention task started (every %ss)", config.retention.prune_interval_seconds)

    yield

    logger.info("LIOS relay shutting down")
    if _retention_task is not None:
        await _retention_task.stop()
        _retention_task = None
    await close_database()


def create_app() -> ASGIApp:
    """Create the LIOS relay ASGI application."""
    config = get_config()
    app = FastAPI(title="LIOS Relay", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    for router in all_routers:
        app.include_router(router)

    return app
