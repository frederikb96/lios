"""Pydantic wire types shared by the relay and every client -- the one place these shapes are
defined, so relay and client code cannot drift apart on what a request or response contains.

These describe clear (relay-visible) metadata only. What travels inside a sealed blob
(filename, MIME type, the payload itself) is defined by :mod:`lios_protocol.framing`, not
here -- the relay never constructs or reads one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Platform = Literal["ios", "linux"]


class ItemSummary(BaseModel):
    """One item's clear metadata, as returned by the catch-up list and the stream.

    `target_device_id` is `None` for a broadcast item -- delivered to every paired device
    other than the sender. Set, it narrows delivery (and the ack that triggers pruning) to
    that one device.
    """

    id: UUID
    sender_device_id: UUID
    target_device_id: UUID | None
    size_bytes: int
    created_at: datetime


class ItemCreated(BaseModel):
    """Response to `POST /api/items`."""

    id: UUID
    created_at: datetime


class StreamEvent(BaseModel):
    """One message sent down `GET /api/stream` when a new item arrives.

    The stream only ever announces items created after the socket connected -- a client
    reconnecting after time offline must follow up with `GET /api/items?since=` to catch up
    on anything it missed while disconnected. See the relay's stream endpoint for the full
    reconnect contract.
    """

    type: Literal["item.new"] = "item.new"
    item: ItemSummary


class DeviceInfo(BaseModel):
    """One paired device, as returned by the device registry."""

    id: UUID
    display_name: str
    platform: Platform
    created_at: datetime
    has_push_token: bool


class PairingSessionCreated(BaseModel):
    """Response to `POST /api/devices/pairing-sessions`."""

    pairing_code: str
    expires_at: datetime


class PairingRedeem(BaseModel):
    """Request body for `POST /api/devices/pair`."""

    pairing_code: str
    platform: Platform
    display_name: str


class DeviceBootstrap(BaseModel):
    """Request body for `POST /api/devices/bootstrap` -- registering the very first device.

    Every later device joins through :class:`PairingRedeem`, which requires an existing
    device's token to mint the code it redeems. Something has to be the first, with no
    predecessor to ask -- this is that one exception, and the relay only accepts it while its
    device registry is still empty.
    """

    platform: Platform
    display_name: str


class DevicePaired(BaseModel):
    """Response to `POST /api/devices/pair` -- the new device's own credential.

    `device_token` is shown exactly once, here -- the relay stores only its hash and cannot
    display it again afterwards.
    """

    device_id: UUID
    device_token: str


class PushTokenUpdate(BaseModel):
    """Request body for `POST /api/devices/{id}/push-token`."""

    apns_token: str
