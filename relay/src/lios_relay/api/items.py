"""Items: `POST /api/items`, `GET /api/items/{id}`, `GET /api/items?since=`, `DELETE
/api/items/{id}`.

The two content endpoints (create, fetch) carry the sealed blob as a raw `application/
octet-stream` body -- not JSON with the blob base64-encoded -- so an encrypted photo does not
pay a 33% size penalty getting there. Everything else (the catch-up list, the stream) is
JSON built from `lios_protocol.wire.ItemSummary`, which never includes the blob itself.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from lios_protocol.wire import ItemCreated, ItemSummary, StreamEvent
from sqlalchemy.ext.asyncio import AsyncSession

from lios_relay.auth import require_device
from lios_relay.config import RelayConfig, get_config
from lios_relay.database.models import Device, Item
from lios_relay.database.repository import (
    ack_item,
    create_item,
    get_device,
    get_item,
    list_items_since,
    list_other_device_ids,
)
from lios_relay.push import PushUnavailable, send_new_item_push
from lios_relay.server_state import get_broadcaster, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/items", tags=["items"])


def _item_summary(item: Item) -> ItemSummary:
    """Build the clear-metadata view of an `Item` row that ever leaves the process."""
    return ItemSummary(
        id=item.id,
        sender_device_id=item.sender_device_id,
        target_device_id=item.target_device_id,
        size_bytes=item.size_bytes,
        created_at=item.created_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item_endpoint(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    device: Annotated[Device, Depends(require_device)],
    target_device_id: uuid.UUID | None = Query(
        default=None,
        description="Narrow delivery to one device; omitted means every other paired device.",
    ),
) -> ItemCreated:
    """Store a sealed item and notify every intended recipient.

    Bounded by `items.max_size_bytes` -- rejected with 413 before the whole body is even
    read, via `Content-Length`, so an oversized upload cannot exhaust memory on its way to
    being rejected. A client that cannot report `Content-Length` (unusual for a native HTTP
    client posting a bounded, already-sealed blob in memory) is refused with 411 rather than
    read unbounded.
    """
    config = get_config()
    content_length = request.headers.get("content-length")
    if content_length is None:
        raise HTTPException(
            status_code=status.HTTP_411_LENGTH_REQUIRED, detail="Content-Length is required"
        )
    if int(content_length) > config.items.max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"item exceeds items.max_size_bytes ({config.items.max_size_bytes})",
        )

    sealed_blob = await request.body()
    if len(sealed_blob) > config.items.max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"item exceeds items.max_size_bytes ({config.items.max_size_bytes})",
        )
    if not sealed_blob:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty body")

    if target_device_id is not None:
        target = await get_device(session, target_device_id)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="target_device_id not found"
            )
        recipient_ids = [target_device_id]
    else:
        recipient_ids = await list_other_device_ids(session, exclude=device.id)

    item = await create_item(
        session,
        sender_device_id=device.id,
        target_device_id=target_device_id,
        sealed_blob=sealed_blob,
        recipient_ids=recipient_ids,
    )
    await session.flush()

    event = StreamEvent(item=_item_summary(item))
    get_broadcaster().publish(event.model_dump_json())

    await _push_to_recipients(session, config, recipient_ids, item.id)

    return ItemCreated(id=item.id, created_at=item.created_at)


async def _push_to_recipients(
    session: AsyncSession, config: RelayConfig, recipient_ids: list[uuid.UUID], item_id: uuid.UUID
) -> None:
    """Best-effort APNs push to every recipient that is an iOS device with a push token.

    Never raises: a push failure is logged and otherwise invisible to the caller of
    `POST /api/items`, since the item is already durably stored regardless of whether any
    push goes out.
    """
    tokens: list[str] = []
    for recipient_id in recipient_ids:
        recipient = await get_device(session, recipient_id)
        if recipient is not None and recipient.platform == "ios" and recipient.apns_token:
            tokens.append(recipient.apns_token)

    if not tokens:
        return
    try:
        await send_new_item_push(config=config.apns, tokens=tokens, item_id=item_id)
    except PushUnavailable:
        pass
    except Exception:
        logger.exception("push failed for item %s", item_id)


@router.get("/{item_id}")
async def get_item_endpoint(
    item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _device: Annotated[Device, Depends(require_device)],
) -> Response:
    """Fetch one item's sealed blob, raw."""
    item = await get_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
    return Response(content=item.sealed_blob, media_type="application/octet-stream")


@router.get("")
async def list_items_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _device: Annotated[Device, Depends(require_device)],
    since: datetime = Query(
        default=datetime.fromtimestamp(0, tz=UTC),
        description="Return items created strictly after this timestamp -- the catch-up list "
        "for a client that was offline while the stream was announcing new items.",
    ),
) -> list[ItemSummary]:
    """Catch-up list: every item's clear metadata, created after `since`."""
    items = await list_items_since(session, since)
    return [_item_summary(item) for item in items]


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def ack_item_endpoint(
    item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    device: Annotated[Device, Depends(require_device)],
) -> None:
    """A device confirming it has taken an item.

    Never a hard failure for an item that is already gone (pruned by retention, or already
    fully acked by everyone else) -- the caller's own job here is done either way.
    """
    item = await get_item(session, item_id)
    if item is None:
        return None
    await ack_item(session, item_id, device.id)
    return None
