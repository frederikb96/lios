"""Item envelope round-trip through real `lios_protocol` framing and crypto -- no mocks.

Proves the metadata-key convention (`kind`, `filename`, `content_type`) survives seal/open
intact, and that a wrong key is rejected rather than silently producing garbage.
"""

from __future__ import annotations

import pytest
from lios_protocol.crypto import TamperError, generate_group_key

from lios_linux.relaylink.item_codec import build_sealed_item, open_sealed_item


def test_text_item_round_trips_with_no_filename_or_content_type() -> None:
    key = generate_group_key()
    sealed = build_sealed_item(group_key=key, kind="text", payload=b"hello from linux")

    decoded = open_sealed_item(group_key=key, sealed_blob=sealed)

    assert decoded.kind == "text"
    assert decoded.filename is None
    assert decoded.content_type is None
    assert decoded.payload == b"hello from linux"


def test_image_item_round_trips_with_filename_and_content_type() -> None:
    key = generate_group_key()
    sealed = build_sealed_item(
        group_key=key,
        kind="image",
        payload=b"\x89PNG-fake-bytes",
        filename="screenshot.png",
        content_type="image/png",
    )

    decoded = open_sealed_item(group_key=key, sealed_blob=sealed)

    assert decoded.kind == "image"
    assert decoded.filename == "screenshot.png"
    assert decoded.content_type == "image/png"
    assert decoded.payload == b"\x89PNG-fake-bytes"


def test_wrong_group_key_is_rejected_as_tampering() -> None:
    sealed = build_sealed_item(group_key=generate_group_key(), kind="text", payload=b"secret")

    with pytest.raises(TamperError):
        open_sealed_item(group_key=generate_group_key(), sealed_blob=sealed)


def test_associated_data_mismatch_is_rejected() -> None:
    key = generate_group_key()
    sealed = build_sealed_item(
        group_key=key, kind="text", payload=b"secret", associated_data=b"item-id-1"
    )

    with pytest.raises(TamperError):
        open_sealed_item(group_key=key, sealed_blob=sealed, associated_data=b"item-id-2")
