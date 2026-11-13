"""Sending push for a newly arrived item -- the one place in this service that speaks to the
shared push relay.

The LIOS relay holds no Apple credential and no APNs device token. Each iOS device registers
its token at the push relay itself and hands this service the resulting ticket; a push is one
`POST /v1/push` carrying that ticket and a blob. The push relay forwards the blob to Apple
unopened and the iOS notification extension decodes it (`lios_protocol.push`).

The relay can never read an item's content, so the push is deliberately generic: the push
relay's own fallback banner, plus the item id, sender device id and the opaque
`sealed_preview` inside the blob. That combination is what lets the notification extension
decrypt the preview on-device under the shared group key and rewrite the banner before it is
shown -- the extension never fetches the item's own payload to do this.

Best-effort throughout: a push failure must never turn an otherwise-successful
`POST /api/items` into an error response, since the item itself was already stored and
every other paired device already has (or will get) it through the WebSocket stream.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

import httpx
from lios_protocol.headers import PUSH_RELAY_APP
from lios_protocol.push import build_push_blob

from lios_relay.config import PushConfig

logger = logging.getLogger(__name__)

#: Statuses of `POST /v1/push` after which the ticket is useless for good: 410 means Apple
#: refused the device token permanently, 401 that the ticket is invalid or expired. Either
#: way the phone has to register again.
_TICKET_DEAD_STATUSES = frozenset({401, 410})
_PAYLOAD_TOO_LARGE = 413


class PushUnavailable(RuntimeError):
    """No push relay configured, or no ticket was given to send to."""


@dataclass(frozen=True)
class PushTarget:
    """One device to push to: its id (to clear a dead ticket) and its push relay ticket."""

    device_id: uuid.UUID
    ticket: str


async def send_new_item_push(
    *,
    config: PushConfig,
    targets: list[PushTarget],
    item_id: uuid.UUID,
    sender_device_id: uuid.UUID,
    sealed_preview: bytes | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[uuid.UUID]:
    """Push a generic "new item" notification to every device in `targets`.

    `sealed_preview`, if the sender attached one, rides inside the blob exactly as received
    -- this module has no group key and never opens it. A push relay that refuses the blob as
    too large gets it again without the preview: a generic banner beats none.

    Returns the ids of the devices whose ticket the push relay rejected for good -- the
    caller owns clearing those, since this module has no database access of its own.

    Raises:
        PushUnavailable: no push relay is configured, or `targets` is empty. Both are normal
            outcomes (a self-hosted relay with push off; every registered device is Linux),
            never logged as an error by the caller.
    """
    if not config.enabled:
        raise PushUnavailable("no push relay is configured")
    if not targets:
        raise PushUnavailable("no device ticket to push to")

    url = config.relay_url.rstrip("/") + "/v1/push"
    blobs = [
        build_push_blob(
            item_id=item_id, sender_device_id=sender_device_id, sealed_preview=sealed_preview
        )
    ]
    if sealed_preview:
        blobs.append(
            build_push_blob(item_id=item_id, sender_device_id=sender_device_id, sealed_preview=None)
        )

    async with httpx.AsyncClient(
        timeout=config.send_timeout_seconds, transport=transport
    ) as client:

        async def _send_one(target: PushTarget) -> uuid.UUID | None:
            """Returns the device id when its ticket is dead, otherwise None."""
            try:
                for blob in blobs:
                    response = await client.post(
                        url,
                        json={
                            "app": PUSH_RELAY_APP,
                            "ticket": target.ticket,
                            "type": "alert",
                            "blob": blob,
                            "ttl_seconds": config.ttl_seconds,
                        },
                    )
                    if response.status_code != _PAYLOAD_TOO_LARGE:
                        break
                    logger.warning("push relay refused the blob as too large; retrying without it")
            except httpx.HTTPError as e:
                logger.warning("push relay unreachable: %s", e)
                return None

            if response.status_code == 202:
                return None
            if response.status_code in _TICKET_DEAD_STATUSES:
                return target.device_id
            logger.warning("push relay answered %s", response.status_code)
            return None

        results = await asyncio.gather(*(_send_one(t) for t in targets))

    return [device_id for device_id in results if device_id is not None]
