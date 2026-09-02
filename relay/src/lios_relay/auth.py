"""Bearer device-token authentication.

Every endpoint except `GET /health`, `POST /api/devices/pair` and the pairing-session create
(which itself requires an existing device's token) sits behind :func:`require_device`. LIOS
carries its own auth end to end -- there is deliberately no oauth2-proxy / ForwardAuth in
front of the relay, since that would also break the WebSocket upgrade on `/api/stream`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from lios_relay.database.models import Device
from lios_relay.database.repository import get_device_by_token
from lios_relay.server_state import get_session

_bearer_scheme = HTTPBearer(description="Device bearer token, issued at pairing.")


async def require_device(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Device:
    """Resolve the bearer token on the request to its `Device`, or reject the request.

    A wrong or unrecognised token and a well-formed but never-issued one answer identically
    -- 401, no detail beyond "invalid device token" -- so a caller cannot use the response to
    distinguish a typo from a revoked device.
    """
    device = await get_device_by_token(session, credentials.credentials)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid device token"
        )
    return device
