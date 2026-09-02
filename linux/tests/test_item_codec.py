"""Item envelope round-trip through real `lios_protocol` framing and crypto -- no mocks.

Proves the wire metadata-key convention (`type`, `filename`, `mime_type` -- matching LIOSKit's
`FrameMetadataKey` exactly, not a Linux-only shape) and the associated-data construction
(`item_id|size_bytes`, matching `LiosItem.seal`/`.open`) survive seal/open intact, and that a
wrong key, id or size is rejected rather than silently producing garbage.
"""

from __future__ import annotations

import pytest
from lios_protocol.crypto import TamperError, generate_group_key

from lios_linux.relaylink.item_codec import (
    build_sealed_item,
    build_sealed_preview,
    open_sealed_item,
    open_sealed_preview,
    truncate_preview_text,
)


def test_text_item_round_trips_with_no_filename_or_content_type() -> None:
    key = generate_group_key()
    sealed = build_sealed_item(
        group_key=key, kind="text", payload=b"hello from linux", item_id="item-1"
    )

    decoded = open_sealed_item(
        group_key=key, sealed_blob=sealed.blob, item_id="item-1", size_bytes=sealed.size_bytes
    )

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
        item_id="item-2",
        filename="screenshot.png",
        content_type="image/png",
    )

    decoded = open_sealed_item(
        group_key=key, sealed_blob=sealed.blob, item_id="item-2", size_bytes=sealed.size_bytes
    )

    assert decoded.kind == "image"
    assert decoded.filename == "screenshot.png"
    assert decoded.content_type == "image/png"
    assert decoded.payload == b"\x89PNG-fake-bytes"


def test_size_bytes_matches_the_actual_blob_length() -> None:
    key = generate_group_key()
    sealed = build_sealed_item(group_key=key, kind="text", payload=b"x", item_id="item-3")

    assert sealed.size_bytes == len(sealed.blob)


def test_item_id_is_lowercased_before_authentication() -> None:
    """An uppercase id (as Swift's `uuidString` would produce) authenticates identically to
    its lowercase form, since both platforms lowercase before building associated data."""
    key = generate_group_key()
    sealed = build_sealed_item(
        group_key=key, kind="text", payload=b"hi", item_id="ABCDEF12-0000-0000-0000-000000000000"
    )

    decoded = open_sealed_item(
        group_key=key,
        sealed_blob=sealed.blob,
        item_id="abcdef12-0000-0000-0000-000000000000",
        size_bytes=sealed.size_bytes,
    )

    assert decoded.payload == b"hi"


def test_wrong_group_key_is_rejected_as_tampering() -> None:
    sealed = build_sealed_item(
        group_key=generate_group_key(), kind="text", payload=b"secret", item_id="item-4"
    )

    with pytest.raises(TamperError):
        open_sealed_item(
            group_key=generate_group_key(),
            sealed_blob=sealed.blob,
            item_id="item-4",
            size_bytes=sealed.size_bytes,
        )


def test_wrong_item_id_is_rejected() -> None:
    key = generate_group_key()
    sealed = build_sealed_item(group_key=key, kind="text", payload=b"secret", item_id="item-5")

    with pytest.raises(TamperError):
        open_sealed_item(
            group_key=key,
            sealed_blob=sealed.blob,
            item_id="item-other",
            size_bytes=sealed.size_bytes,
        )


def test_wrong_size_bytes_is_rejected() -> None:
    key = generate_group_key()
    sealed = build_sealed_item(group_key=key, kind="text", payload=b"secret", item_id="item-6")

    with pytest.raises(TamperError):
        open_sealed_item(
            group_key=key,
            sealed_blob=sealed.blob,
            item_id="item-6",
            size_bytes=sealed.size_bytes + 1,
        )


def test_sealed_preview_round_trips_for_text() -> None:
    key = generate_group_key()
    sealed = build_sealed_preview(
        group_key=key, item_id="item-7", kind="text", preview="hello there", filename=None
    )

    preview = open_sealed_preview(group_key=key, sealed_blob=sealed, item_id="item-7")

    assert preview is not None
    assert preview.kind == "text"
    assert preview.preview == "hello there"
    assert preview.filename is None


def test_sealed_preview_round_trips_for_a_file_with_no_text_preview() -> None:
    key = generate_group_key()
    sealed = build_sealed_preview(
        group_key=key, item_id="item-8", kind="file", preview=None, filename="report.pdf"
    )

    preview = open_sealed_preview(group_key=key, sealed_blob=sealed, item_id="item-8")

    assert preview is not None
    assert preview.kind == "file"
    assert preview.preview is None
    assert preview.filename == "report.pdf"


def test_empty_sealed_preview_bytes_means_no_preview_was_attached() -> None:
    assert open_sealed_preview(group_key=generate_group_key(), sealed_blob=b"", item_id="x") is None


def test_sealed_preview_wrong_item_id_is_rejected() -> None:
    key = generate_group_key()
    sealed = build_sealed_preview(
        group_key=key, item_id="item-9", kind="text", preview="hi", filename=None
    )

    with pytest.raises(TamperError):
        open_sealed_preview(group_key=key, sealed_blob=sealed, item_id="item-other")


def test_truncate_preview_text_leaves_short_text_untouched() -> None:
    assert truncate_preview_text("short") == "short"


def test_truncate_preview_text_shortens_long_text_with_ellipsis() -> None:
    text = "x" * 200
    truncated = truncate_preview_text(text, limit=120)
    assert len(truncated) == 120
    assert truncated.endswith("...")
