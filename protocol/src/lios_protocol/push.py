"""The push blob: what the LIOS server hands the shared push relay for one new item.

The push relay forwards the blob to Apple unopened, and the iOS notification extension decodes
it: base64 of a JSON object carrying the item id, the sender's device id and, when the sender
attached one, the sealed preview (itself base64, still sealed under the group key). The ids are
the same clear metadata `ItemSummary` already carries; the preview stays opaque to everything
between the sender and the phone.
"""

from __future__ import annotations

import base64
import json
import uuid

from lios_protocol.headers import (
    PUSH_ITEM_ID_KEY,
    PUSH_SEALED_PREVIEW_KEY,
    PUSH_SENDER_DEVICE_ID_KEY,
)


def build_push_blob(
    *, item_id: uuid.UUID, sender_device_id: uuid.UUID, sealed_preview: bytes | None
) -> str:
    """Encode one item's push blob. The preview key is omitted entirely when there is none."""
    fields: dict[str, str] = {
        PUSH_ITEM_ID_KEY: str(item_id),
        PUSH_SENDER_DEVICE_ID_KEY: str(sender_device_id),
    }
    if sealed_preview:
        fields[PUSH_SEALED_PREVIEW_KEY] = base64.b64encode(sealed_preview).decode("ascii")
    return base64.b64encode(json.dumps(fields, separators=(",", ":")).encode("utf-8")).decode(
        "ascii"
    )
