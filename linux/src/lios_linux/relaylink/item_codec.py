"""Building and opening one item's sealed envelope -- framing and encryption composed.

Metadata keys inside the frame (`lios_protocol.framing` deliberately knows nothing about what
its bytes mean -- see its module docstring, so this convention lives here instead): `kind` is
`"text"`, `"image"` or `"file"`; `filename` and `content_type` are present for `image`/`file`
items and absent for a `text` item, which needs neither. This is a convention the Linux and
iOS clients must agree on; the relay never reads any of it.
"""

from __future__ import annotations

from dataclasses import dataclass

from lios_protocol import crypto, framing

_KIND_KEY = "kind"
_FILENAME_KEY = "filename"
_CONTENT_TYPE_KEY = "content_type"


@dataclass(frozen=True)
class DecodedItem:
    """One item's metadata and payload, after opening its sealed envelope."""

    kind: str
    filename: str | None
    content_type: str | None
    payload: bytes


def build_sealed_item(
    *,
    group_key: bytes,
    kind: str,
    payload: bytes,
    filename: str | None = None,
    content_type: str | None = None,
    associated_data: bytes = b"",
) -> bytes:
    """Frame `payload` with its metadata, then seal it under the fleet's group key."""
    metadata = {_KIND_KEY: kind}
    if filename is not None:
        metadata[_FILENAME_KEY] = filename
    if content_type is not None:
        metadata[_CONTENT_TYPE_KEY] = content_type
    frame = framing.pack(metadata, payload)
    return crypto.seal(group_key, frame, associated_data=associated_data)


def open_sealed_item(
    *, group_key: bytes, sealed_blob: bytes, associated_data: bytes = b""
) -> DecodedItem:
    """Reverse :func:`build_sealed_item`.

    Raises:
        ValueError: the blob is malformed, or the frame's metadata does not parse.
        lios_protocol.crypto.TamperError: the blob failed authentication.
    """
    frame = crypto.open_sealed(group_key, sealed_blob, associated_data=associated_data)
    metadata, payload = framing.unpack(frame)
    return DecodedItem(
        kind=metadata.get(_KIND_KEY, "file"),
        filename=metadata.get(_FILENAME_KEY),
        content_type=metadata.get(_CONTENT_TYPE_KEY),
        payload=payload,
    )
