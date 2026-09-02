"""Round-trip tests for :mod:`lios_protocol.framing`."""

from __future__ import annotations

import pytest

from lios_protocol.framing import pack, unpack


def test_pack_unpack_round_trip() -> None:
    metadata = {"filename": "cat.png", "mime_type": "image/png"}
    payload = b"\x89PNG\r\n\x1a\nnot really a png"
    frame = pack(metadata, payload)
    assert unpack(frame) == (metadata, payload)


def test_pack_unpack_empty_payload() -> None:
    metadata = {"filename": "empty.txt"}
    assert unpack(pack(metadata, b"")) == (metadata, b"")


def test_pack_unpack_empty_metadata() -> None:
    payload = b"just text on the clipboard"
    assert unpack(pack({}, payload)) == ({}, payload)


def test_pack_preserves_unicode_metadata() -> None:
    metadata = {"filename": "Uebersicht – Notizen.pdf"}
    assert unpack(pack(metadata, b"pdf-bytes"))[0] == metadata


def test_payload_is_not_base64_inflated() -> None:
    """The payload rides raw in the frame -- only the metadata is JSON-encoded."""
    payload = bytes(range(256)) * 10
    frame = pack({}, payload)
    assert frame.endswith(payload)


def test_unpack_rejects_frame_shorter_than_prefix() -> None:
    with pytest.raises(ValueError, match="length prefix"):
        unpack(b"\x00\x00")


def test_unpack_rejects_truncated_metadata() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        unpack(b"\x00\x00\x00\x10short")
