"""Packing an item's metadata and payload into one buffer before it is sealed.

Kept separate from :mod:`lios_protocol.crypto`: encryption operates on arbitrary bytes and
knows nothing about what is inside them; this module defines what those bytes mean. Metadata
that would leak content if left in the clear -- filename, MIME type, a text preview -- lives
here, inside the sealed envelope, never as a clear relay-visible field.
"""

from __future__ import annotations

import json
import struct

#: Metadata length prefix: unsigned 32-bit big-endian, far larger than any item's metadata
#: will ever be.
_LENGTH_PREFIX = struct.Struct(">I")


def pack(metadata: dict[str, str], payload: bytes) -> bytes:
    """Concatenate `metadata` (as length-prefixed JSON) and `payload` into one buffer.

    The payload is appended raw, never base64-encoded -- avoiding that overhead is the whole
    reason this is a length-prefixed binary frame rather than one JSON document with the
    payload embedded as a string field.
    """
    metadata_bytes = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    return _LENGTH_PREFIX.pack(len(metadata_bytes)) + metadata_bytes + payload


def unpack(frame: bytes) -> tuple[dict[str, str], bytes]:
    """Reverse :func:`pack`, returning the metadata dict and the raw payload.

    Raises:
        ValueError: `frame` is shorter than the length prefix, or the prefix claims more
            metadata bytes than `frame` actually holds.
    """
    if len(frame) < _LENGTH_PREFIX.size:
        raise ValueError("frame shorter than the metadata length prefix")
    (metadata_len,) = _LENGTH_PREFIX.unpack_from(frame)
    start = _LENGTH_PREFIX.size
    end = start + metadata_len
    if end > len(frame):
        raise ValueError("frame's metadata length prefix exceeds the frame's own size")
    metadata: dict[str, str] = json.loads(frame[start:end].decode("utf-8"))
    return metadata, frame[end:]
