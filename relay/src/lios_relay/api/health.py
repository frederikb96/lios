"""`GET /health` and `GET /health/live` -- for the Kubernetes probes. Unauthenticated, on
purpose: a probe has no device token, and this must stay reachable even while every device
token is broken.

Split in two so a transient database outage cannot start a restart loop: liveness (process is
up, never touches the database) must not fail just because Postgres is briefly unreachable --
restarting the relay pod does nothing to fix that, and only adds a second failure to debug on
top of the first. Readiness is the one that actually checks the database, since only that one
controls whether traffic is routed to this pod.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lios_relay.server_state import get_session

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def health_live() -> JSONResponse:
    """Liveness: the process is up. Never touches the database."""
    return JSONResponse(status_code=200, content={"status": "alive"})


@router.get("/health")
async def health(session: Annotated[AsyncSession, Depends(get_session)]) -> JSONResponse:
    """Readiness: the database is reachable."""
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={"status": "ok" if db_ok else "not_ready", "database": "ok" if db_ok else "error"},
    )
