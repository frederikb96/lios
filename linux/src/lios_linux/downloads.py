"""Where a received item lands on disk, and under what name.

The name a sender supplies is only a suggestion: it crosses a device boundary, so it is
sanitised down to a single path component before it is ever joined to a directory. An item
that arrives with no name at all still gets a readable, typed one derived from its MIME
type, because a bare identifier with no extension tells the person who saved it nothing.
"""

from __future__ import annotations

import mimetypes
import re
from datetime import datetime
from pathlib import Path

# Anything that could escape the target directory or confuse a file manager.
_UNSAFE = re.compile(r"[\x00-\x1f]")
_MAX_STEM = 200
_FALLBACK_EXTENSION = ".bin"

# `mimetypes` answers these with an extension that is either absent, or correct but
# unrecognisable on sight (`.jpe` for a JPEG).
_EXTENSION_OVERRIDES = {
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
}


def extension_for(content_type: str | None) -> str:
    """The file extension a MIME type implies, including the leading dot."""
    if not content_type:
        return _FALLBACK_EXTENSION
    base = content_type.split(";", 1)[0].strip().lower()
    override = _EXTENSION_OVERRIDES.get(base)
    if override is not None:
        return override
    return mimetypes.guess_extension(base) or _FALLBACK_EXTENSION


def sanitize(filename: str) -> str | None:
    """A sender's filename reduced to a safe single path component, or `None` if nothing
    usable survives -- an empty name, a bare `.`/`..`, or a name that was only separators."""
    candidate = _UNSAFE.sub("", filename).replace("\\", "/").rsplit("/", 1)[-1].strip()
    if candidate in ("", ".", ".."):
        return None
    suffix = Path(candidate).suffix
    stem = candidate[: len(candidate) - len(suffix)]
    return stem[:_MAX_STEM] + suffix


def save_name(
    *,
    filename: str | None,
    content_type: str | None,
    now: datetime,
) -> str:
    """The name to save an item under: the sender's own, sanitised, or a timestamped one
    carrying the extension its MIME type implies."""
    if filename is not None:
        safe = sanitize(filename)
        if safe is not None:
            return safe
    return f"lios-{now:%Y%m%d-%H%M%S}{extension_for(content_type)}"


def unique_path(directory: Path, name: str) -> Path:
    """`directory/name`, with a counter appended to the stem while that path is taken --
    two files sharing a name is the ordinary case (a phone numbers its photos per device,
    not per recipient), and overwriting the earlier one loses it silently."""
    suffix = Path(name).suffix
    stem = name[: len(name) - len(suffix)]
    candidate = directory / name
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate
