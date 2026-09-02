"""Device registry and pairing: `POST /api/devices/bootstrap`, `POST
/api/devices/pairing-sessions`, `POST /api/devices/pair`, `POST /api/devices/{id}/push-token`.

The group key never appears anywhere in this module -- it travels only inside the QR payload
`lios_protocol.pairing` builds, entirely client-side. All the relay ever mints or redeems is
an opaque pairing code.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from lios_protocol.pairing import generate_pairing_code
from lios_protocol.wire import (
    DeviceBootstrap,
    DevicePaired,
    PairingRedeem,
    PairingSessionCreated,
    PushTokenUpdate,
)
from sqlalchemy.ext.asyncio import AsyncSession

from lios_relay.auth import require_device
from lios_relay.config import get_config
from lios_relay.database.models import Device
from lios_relay.database.repository import (
    create_device,
    create_pairing_session,
    generate_device_token,
    list_devices,
    redeem_pairing_session,
    set_push_token,
)
from lios_relay.server_state import get_session

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
async def bootstrap_first_device(
    body: DeviceBootstrap, session: Annotated[AsyncSession, Depends(get_session)]
) -> DevicePaired:
    """Register the very first device in an otherwise-empty fleet. No token required.

    Refused once any device already exists -- from that point on, every further device joins
    through `POST /api/devices/pair`, which does require one. A freshly deployed relay with
    zero paired devices is the only window this is ever reachable in.
    """
    existing = await list_devices(session)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="a device is already registered -- use POST /api/devices/pair instead",
        )

    token = generate_device_token()
    device = await create_device(
        session, display_name=body.display_name, platform=body.platform, token=token
    )
    return DevicePaired(device_id=device.id, device_token=token)


@router.post("/pairing-sessions", status_code=status.HTTP_201_CREATED)
async def create_pairing_session_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    device: Annotated[Device, Depends(require_device)],
) -> PairingSessionCreated:
    """Mint a fresh pairing code on behalf of the caller's own already-paired device.

    Requires an existing device token -- a stranger cannot mint codes for a fleet they are
    not already part of. The caller embeds the returned code, together with the group key it
    already holds, into the QR code the new device scans.
    """
    config = get_config()
    code = generate_pairing_code()
    pairing_session = await create_pairing_session(
        session, requested_by=device.id, code=code, ttl_seconds=config.pairing.code_ttl_seconds
    )
    return PairingSessionCreated(pairing_code=code, expires_at=pairing_session.expires_at)


@router.post("/pair", status_code=status.HTTP_201_CREATED)
async def pair_device(
    body: PairingRedeem, session: Annotated[AsyncSession, Depends(get_session)]
) -> DevicePaired:
    """Redeem a pairing code for a new device token. The one endpoint that needs no token.

    A code that never existed, already expired, or was already redeemed all answer the same
    401 -- see `redeem_pairing_session`'s own doc comment for why.
    """
    pairing_session = await redeem_pairing_session(session, body.pairing_code)
    if pairing_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="pairing code is invalid, expired, or already used",
        )

    token = generate_device_token()
    device = await create_device(
        session, display_name=body.display_name, platform=body.platform, token=token
    )
    return DevicePaired(device_id=device.id, device_token=token)


@router.post("/{device_id}/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def update_push_token(
    device_id: uuid.UUID,
    body: PushTokenUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    device: Annotated[Device, Depends(require_device)],
) -> None:
    """Register an APNs token for `device_id` -- always the caller's own device.

    `device_id` in the path must match the authenticated device: one device cannot register
    a push token on another's behalf.
    """
    if device.id != device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cannot set a push token for a different device",
        )
    updated = await set_push_token(session, device_id, body.apns_token)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")
