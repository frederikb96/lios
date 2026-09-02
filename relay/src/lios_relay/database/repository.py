"""Data access for the relay's four tables.

Plain async functions over a caller-supplied `AsyncSession` rather than repository classes --
each request already gets its own session from the `get_session` FastAPI dependency, so there
is no separate lifecycle here worth wrapping in a class.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from lios_relay.database.models import Device, Item, ItemAck, ItemRecipient, PairingSession


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a bearer token or pairing code -- what is actually stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_device_token() -> str:
    """A fresh, high-entropy bearer token for a newly paired device."""
    return secrets.token_urlsafe(32)


async def get_device_by_token(session: AsyncSession, token: str) -> Device | None:
    """Look up a device by its raw bearer token (hashed before the query, never logged)."""
    result = await session.execute(
        select(Device).where(Device.token_hash == hash_token(token))
    )
    return result.scalar_one_or_none()


async def get_device(session: AsyncSession, device_id: uuid.UUID) -> Device | None:
    """Look up a device by id."""
    return await session.get(Device, device_id)


async def list_devices(session: AsyncSession) -> list[Device]:
    """Every currently paired device."""
    result = await session.execute(select(Device).order_by(Device.created_at))
    return list(result.scalars().all())


async def list_other_device_ids(session: AsyncSession, exclude: uuid.UUID) -> list[uuid.UUID]:
    """Every paired device's id except `exclude` -- the broadcast recipient set."""
    result = await session.execute(select(Device.id).where(Device.id != exclude))
    return list(result.scalars().all())


async def set_push_token(
    session: AsyncSession, device_id: uuid.UUID, apns_token: str
) -> Device | None:
    """Record (or replace) a device's APNs token. Returns None if the device does not exist."""
    device = await session.get(Device, device_id)
    if device is None:
        return None
    device.apns_token = apns_token
    return device


async def create_pairing_session(
    session: AsyncSession, *, requested_by: uuid.UUID, code: str, ttl_seconds: int
) -> PairingSession:
    """Mint a new single-use pairing code on behalf of an already-paired device."""
    pairing_session = PairingSession(
        code_hash=hash_token(code),
        requested_by_device_id=requested_by,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    session.add(pairing_session)
    await session.flush()
    return pairing_session


async def redeem_pairing_session(session: AsyncSession, code: str) -> PairingSession | None:
    """Consume a pairing code, returning the session if it was valid and unused.

    Returns None for a code that never existed, already expired, or was already redeemed --
    the caller cannot distinguish which, by design: telling an attacker which reason applies
    would confirm whether a guessed code was ever real.
    """
    result = await session.execute(
        select(PairingSession).where(PairingSession.code_hash == hash_token(code))
    )
    pairing_session = result.scalar_one_or_none()
    if pairing_session is None:
        return None
    if pairing_session.redeemed_at is not None:
        return None
    if pairing_session.expires_at < datetime.now(UTC):
        return None
    pairing_session.redeemed_at = datetime.now(UTC)
    return pairing_session


async def create_device(
    session: AsyncSession, *, display_name: str, platform: str, token: str
) -> Device:
    """Register a newly paired device, storing only its token's hash."""
    device = Device(display_name=display_name, platform=platform, token_hash=hash_token(token))
    session.add(device)
    await session.flush()
    return device


async def create_item(
    session: AsyncSession,
    *,
    sender_device_id: uuid.UUID,
    target_device_id: uuid.UUID | None,
    sealed_blob: bytes,
    recipient_ids: list[uuid.UUID],
) -> Item:
    """Store a sealed item and snapshot the devices it is waiting on.

    `recipient_ids` is the set the caller already resolved (either `[target_device_id]` or
    every other currently-paired device) -- kept as an explicit parameter rather than
    re-derived here, so the same list that decides `ItemRecipient` rows is also what a caller
    can use to decide which devices to push to.
    """
    item = Item(
        sender_device_id=sender_device_id,
        target_device_id=target_device_id,
        sealed_blob=sealed_blob,
        size_bytes=len(sealed_blob),
    )
    session.add(item)
    await session.flush()
    for device_id in recipient_ids:
        session.add(ItemRecipient(item_id=item.id, device_id=device_id))
    return item


async def get_item(session: AsyncSession, item_id: uuid.UUID) -> Item | None:
    """Look up one item by id."""
    return await session.get(Item, item_id)


async def list_items_since(session: AsyncSession, since: datetime) -> list[Item]:
    """Every item created strictly after `since`, oldest first -- the catch-up list."""
    result = await session.execute(
        select(Item).where(Item.created_at > since).order_by(Item.created_at)
    )
    return list(result.scalars().all())


async def ack_item(session: AsyncSession, item_id: uuid.UUID, device_id: uuid.UUID) -> None:
    """Record that `device_id` has taken `item_id`. Idempotent -- acking twice is a no-op."""
    existing = await session.get(ItemAck, {"item_id": item_id, "device_id": device_id})
    if existing is not None:
        return
    session.add(ItemAck(item_id=item_id, device_id=device_id))


async def prune_expired_pairing_sessions(session: AsyncSession) -> int:
    """Delete every pairing session past its expiry, redeemed or not. Returns the row count."""
    result = await session.execute(
        delete(PairingSession).where(PairingSession.expires_at < datetime.now(UTC))
    )
    return cast(CursorResult, result).rowcount or 0
