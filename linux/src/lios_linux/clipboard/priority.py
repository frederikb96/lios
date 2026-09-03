"""Ordered mime-type priority for reading the clipboard.

Pure and display-free: takes whatever mime types the clipboard currently offers -- from
`Gdk.Clipboard.get_formats()` on a paste, or a drop's own content formats -- and decides what
to do, with no Wayland connection or GTK import involved here. Ordered rather than
first-match, because a Nautilus file copy also puts the file's path on the clipboard as
`text/plain` -- a naive "is there text? send it" handler would silently send that string
instead of the file.

Priority, high to low: image/png, then any other image/* -- application/vnd.portal.filetransfer,
then the legacy application/vnd.portal.files -- text/uri-list -- text/plain;charset=utf-8, then
bare text/plain.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

#: The two portal file-list mime types, preferred over `text/uri-list`. GTK4 registers a
#: deserializer for both and does the document-portal round-trip itself; `application/
#: vnd.portal.files` is the same thing under GTK 4.6's earlier, since-renamed type name.
_FILE_TRANSFER_TYPES = ("application/vnd.portal.filetransfer", "application/vnd.portal.files")

#: Plain-text types, least preferred -- present on almost every non-empty clipboard, including
#: ones that also carry richer types this priority list checks first.
_TEXT_TYPES = ("text/plain;charset=utf-8", "text/plain")


class ClipboardKind(str, Enum):
    """What the chosen mime type should be treated as."""

    IMAGE = "image"
    FILE_TRANSFER = "file_transfer"
    URI_LIST = "uri_list"
    TEXT = "text"


@dataclass(frozen=True)
class ClipboardChoice:
    """The mime type `choose_read_type` picked, and how to treat it."""

    kind: ClipboardKind
    mime_type: str


def choose_read_type(available: Iterable[str]) -> ClipboardChoice | None:
    """Pick which mime type to read, given everything the clipboard currently offers.

    Returns `None` if nothing on the clipboard matches any tier -- an empty clipboard, or one
    holding only a type this priority list has no rule for.
    """
    offered = list(available)
    offered_set = set(offered)

    if "image/png" in offered_set:
        return ClipboardChoice(ClipboardKind.IMAGE, "image/png")
    image_type = next((mime for mime in offered if mime.startswith("image/")), None)
    if image_type is not None:
        return ClipboardChoice(ClipboardKind.IMAGE, image_type)

    for file_transfer_type in _FILE_TRANSFER_TYPES:
        if file_transfer_type in offered_set:
            return ClipboardChoice(ClipboardKind.FILE_TRANSFER, file_transfer_type)

    if "text/uri-list" in offered_set:
        return ClipboardChoice(ClipboardKind.URI_LIST, "text/uri-list")

    for text_type in _TEXT_TYPES:
        if text_type in offered_set:
            return ClipboardChoice(ClipboardKind.TEXT, text_type)

    return None
