"""The push blob is decoded by the iOS notification extension: pin its exact shape."""

from __future__ import annotations

import base64
import json
import uuid

from lios_protocol.push import build_push_blob

ITEM_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
SENDER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _decode(blob: str) -> dict[str, str]:
    return json.loads(base64.b64decode(blob, validate=True))


def test_blob_carries_ids_and_the_preview_base64() -> None:
    blob = build_push_blob(item_id=ITEM_ID, sender_device_id=SENDER_ID, sealed_preview=b"\x00\x01")
    assert _decode(blob) == {
        "item_id": str(ITEM_ID),
        "sender_device_id": str(SENDER_ID),
        "sealed_preview": "AAE=",
    }


def test_blob_omits_the_preview_key_when_there_is_none() -> None:
    for missing in (None, b""):
        blob = build_push_blob(item_id=ITEM_ID, sender_device_id=SENDER_ID, sealed_preview=missing)
        assert "sealed_preview" not in _decode(blob)
