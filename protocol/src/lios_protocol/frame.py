"""The metadata key names inside the frame `lios_protocol.framing.pack`/`.unpack` carry.

`framing` itself deliberately knows nothing about what its metadata dict means -- these are
the actual keys the relay's clients agree to use for an item's kind, filename and MIME type,
pinned here so Linux and iOS cannot each invent their own shape and silently fail to
understand each other's items (the AEAD covers the whole frame, so a key mismatch does not
raise -- it decrypts fine and then shows up as an item of unknown kind). The Swift mirror of
these same constants is `LIOSKit`'s `FrameMetadataKey`.
"""

from __future__ import annotations

#: `"text"`, `"image"` or `"file"` -- matches the wire's own `Platform`-style literal, and
#: LIOSKit's `ItemType` raw values.
TYPE_KEY = "type"

#: Present for an `image`/`file` item, absent for `text`.
FILENAME_KEY = "filename"

#: Present for an `image`/`file` item, absent for `text`.
MIME_TYPE_KEY = "mime_type"
