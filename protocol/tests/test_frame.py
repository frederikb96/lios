"""These are just string constants, but a mismatch here decrypts fine and silently shows up
as an item of unknown kind -- pin the exact values every client agrees on."""

from __future__ import annotations

from lios_protocol import frame


def test_frame_metadata_key_names() -> None:
    assert frame.TYPE_KEY == "type"
    assert frame.FILENAME_KEY == "filename"
    assert frame.MIME_TYPE_KEY == "mime_type"
