"""These are just string constants, but a typo here breaks interop silently -- pin the exact
values every client and the relay agree on."""

from __future__ import annotations

from lios_protocol import headers


def test_item_request_header_names() -> None:
    assert headers.ITEM_ID_HEADER == "X-Item-Id"
    assert headers.TARGET_DEVICE_ID_HEADER == "X-Target-Device-Id"
    assert headers.SEALED_PREVIEW_HEADER == "X-Sealed-Preview"


def test_push_payload_field_names() -> None:
    assert headers.PUSH_ITEM_ID_KEY == "item_id"
    assert headers.PUSH_SENDER_DEVICE_ID_KEY == "sender_device_id"
    assert headers.PUSH_SEALED_PREVIEW_KEY == "sealed_preview"
