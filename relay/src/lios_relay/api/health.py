"""`GET /health` -- for the Kubernetes probes. Unauthenticated, on purpose: a probe has no
device token, and this must stay reachable even while every device token is broken."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from lios_relay.server_state import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: Annotated[AsyncSession, Depends(get_session)]) -> JSONResponse:
    """Readiness: process is up and the database is reachable."""
    from sqlalchemy import text

    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={"status": "ok" if db_ok else "not_ready", "database": "ok" if db_ok else "error"},
    )
