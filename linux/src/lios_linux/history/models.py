"""The shape of one history row -- direction, kind, and enough metadata to render it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    """Which way the item travelled."""

    INCOMING = "incoming"
    OUTGOING = "outgoing"


class ItemKind(str, Enum):
    """What the item's payload is, independent of how it arrived on the clipboard."""

    TEXT = "text"
    IMAGE = "image"
    FILE = "file"


@dataclass(frozen=True)
class HistoryItem:
    """One entry in the local history.

    `preview` is a short, already-decrypted rendering: the text itself (truncated) for a text
    item, or the filename for an image or file. Never the whole payload -- that lives in the
    blob file `HistoryStore.add` writes alongside this row, referenced by `id`, or nowhere at
    all for a text item, which is small enough to keep inline.
    """

    id: str
    direction: Direction
    kind: ItemKind
    preview: str
    filename: str | None
    content_type: str | None
    size_bytes: int
    created_at: datetime
