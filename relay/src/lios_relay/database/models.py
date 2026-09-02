"""SQLAlchemy ORM models for the LIOS relay.

Five tables: a device registry, single-use pairing sessions, items (the sealed blobs
themselves, plus the clear metadata the relay is allowed to see), the recipient snapshot
each item was created with, and per-device acks against that snapshot -- what drives early
pruning. Nothing here ever stores a group key or a raw device token -- only the token's
hash, so a leaked database backup carries nothing an attacker can use directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Declarative base for every LIOS relay table."""


class Device(Base):
    """A paired device: a phone or a laptop holding the shared group key.

    `token_hash` is a SHA-256 hex digest of the bearer token handed to the device at pairing
    time -- the raw token exists only in the `DevicePaired` response the device received once
    and is expected to store in its own keychain/secret service.
    """

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    apns_token: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PairingSession(Base):
    """A single-use, short-lived code minted by an already-paired device for a new one.

    `code_hash` rather than the code itself, the same reasoning as `Device.token_hash` -- a
    pairing code is a bearer credential for the few minutes it lives.
    """

    __tablename__ = "pairing_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    requested_by_device_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Item(Base):
    """One sealed blob in transit, plus the clear metadata the relay is allowed to see.

    `sealed_blob` is exactly what `lios_protocol.crypto.seal` produced -- the relay stores
    and forwards it unopened. `target_device_id` is the clear-text record of what the sender
    asked for (`None` meaning broadcast) and is exposed on `ItemSummary`; the actual set of
    devices this item is waiting on is the `ItemRecipient` snapshot taken at creation, which
    is what pruning checks against -- a device pairing after this item was created is never
    silently expected to ack it.
    """

    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    sender_device_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    target_device_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=True
    )
    sealed_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    recipients: Mapped[list[ItemRecipient]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    acks: Mapped[list[ItemAck]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class ItemRecipient(Base):
    """The set of devices an item was waiting on, snapshotted at creation time.

    Recomputing "every paired device" at prune time would mean a device that pairs after an
    item was created is silently expected to have acked something it never received --
    this table is what makes "fully acked" a well-defined, point-in-time question instead.
    """

    __tablename__ = "item_recipients"

    item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )

    item: Mapped[Item] = relationship(back_populates="recipients")


class ItemAck(Base):
    """One device confirming it has taken an item -- what lets the relay prune it early,
    once every row in that item's `ItemRecipient` snapshot has a matching ack here."""

    __tablename__ = "item_acks"

    item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    acked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    item: Mapped[Item] = relationship(back_populates="acks")
