"""Sending APNs pushes for a newly arrived item -- the one place in this service that
speaks to APNs.

The relay can never read an item's content, so the push it sends is deliberately generic:
a plain alert plus `mutable-content: 1` and the item id, sender device id, and an optional
opaque `sealed_preview` riding alongside `aps` (never inside it, which is reserved). That
combination is what lets an iOS Notification Service Extension intercept the push, decrypt
`sealed_preview` on-device under the shared group key, and rewrite the banner before it is
shown -- the extension never fetches the item's own payload to do this. The alert text set
here is only ever seen if the extension does not run for some reason -- it must never claim
to say what the item is.

Best-effort throughout: a push failure must never turn an otherwise-successful
`POST /api/items` into an error response, since the item itself was already stored and
every other paired device already has (or will get) it through the WebSocket stream. See
:func:`send_new_item_push`'s own doc comment for exactly what "best-effort" means here.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid

from aioapns import APNs, NotificationRequest, PushType
from aioapns.common import NotificationResult
from lios_protocol.headers import (
    PUSH_ITEM_ID_KEY,
    PUSH_SEALED_PREVIEW_KEY,
    PUSH_SENDER_DEVICE_ID_KEY,
)

from lios_relay.config import ApnsConfig

logger = logging.getLogger(__name__)

#: The status APNs answers with for a token it will never accept again -- see Apple's
#: "Handling Notification Responses from APNs".
_GONE_STATUS = "410"
_PERMANENTLY_BAD_REASONS = frozenset({"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"})


class PushUnavailable(RuntimeError):
    """No usable APNs key configured, or no token was given to send to."""


async def send_new_item_push(
    *,
    config: ApnsConfig,
    tokens: list[str],
    item_id: uuid.UUID,
    sender_device_id: uuid.UUID,
    sealed_preview: bytes | None,
) -> list[str]:
    """Push a generic "new item" notification to every APNs token in `tokens`.

    `sealed_preview`, if the sender attached one, is forwarded base64-encoded exactly as
    received -- this module has no group key and never opens it. Omitted entirely rather
    than sent empty when absent, so the extension's own "was one attached at all" check
    stays a simple key lookup.

    Returns the subset of `tokens` APNs reported permanently gone (`BadDeviceToken`,
    `Unregistered`, or a 410 status) -- the caller owns removing those from the device
    registry, since this module has no database access of its own.

    Raises:
        PushUnavailable: no APNs key is configured, or `tokens` is empty. Both are normal
            outcomes (a fresh deployment with no key yet; every registered device is Linux),
            never logged as an error by the caller.
    """
    if not config.configured:
        raise PushUnavailable("no APNs key is configured")
    if not tokens:
        raise PushUnavailable("no device token to push to")

    key = base64.b64decode(config.auth_key_b64).decode("utf-8")
    message: dict[str, object] = {
        "aps": {
            "alert": {"title": "LIOS", "body": "New item"},
            "mutable-content": 1,
            "sound": "default",
        },
        PUSH_ITEM_ID_KEY: str(item_id),
        PUSH_SENDER_DEVICE_ID_KEY: str(sender_device_id),
    }
    if sealed_preview:
        message[PUSH_SEALED_PREVIEW_KEY] = base64.b64encode(sealed_preview).decode("ascii")

    client = APNs(
        key=key, key_id=config.key_id, team_id=config.team_id, topic=config.topic,
        use_sandbox=False,
    )

    async def _send_one(token: str) -> tuple[str, NotificationResult | BaseException]:
        request = NotificationRequest(
            device_token=token, message=message, push_type=PushType.ALERT, priority=10,
        )
        try:
            return token, await client.send_notification(request)
        except Exception as e:  # noqa: BLE001 - reported per-token below, never raised here
            return token, e

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(_send_one(t) for t in tokens)),
            timeout=config.send_timeout_seconds,
        )
    finally:
        client.pool.close()

    gone: list[str] = []
    for token, outcome in results:
        if isinstance(outcome, BaseException):
            logger.warning("push failed for a device token: %s", outcome)
            continue
        if outcome.is_successful:
            continue
        if outcome.status == _GONE_STATUS or outcome.description in _PERMANENTLY_BAD_REASONS:
            gone.append(token)
        else:
            logger.warning("APNs rejected a push: %s %s", outcome.status, outcome.description)

    return gone
