"""The ordered, never-first-match mime priority for reading the clipboard.

A Nautilus file copy puts `text/plain` on the clipboard holding the file's path -- a
first-match handler would silently send that string instead of the file. These cases are
taken directly from the clipboard types a real GNOME desktop offers after a Nautilus Ctrl+C.
"""

from __future__ import annotations

from lios_linux.clipboard.priority import ClipboardChoice, ClipboardKind, choose_read_type


def test_nautilus_file_copy_picks_file_transfer_not_the_path_string() -> None:
    """The exact five types a real GNOME desktop offers after Ctrl+C on a file in Nautilus."""
    available = [
        "application/vnd.portal.files",
        "application/vnd.portal.filetransfer",
        "text/uri-list",
        "text/plain;charset=utf-8",
        "x-special/gnome-copied-files",
    ]
    assert choose_read_type(available) == ClipboardChoice(
        ClipboardKind.FILE_TRANSFER, "application/vnd.portal.filetransfer"
    )


def test_legacy_portal_files_type_used_when_filetransfer_absent() -> None:
    available = ["application/vnd.portal.files", "text/plain"]
    assert choose_read_type(available) == ClipboardChoice(
        ClipboardKind.FILE_TRANSFER, "application/vnd.portal.files"
    )


def test_image_png_wins_over_everything_else() -> None:
    available = [
        "image/png",
        "text/uri-list",
        "application/vnd.portal.filetransfer",
        "text/plain",
    ]
    assert choose_read_type(available) == ClipboardChoice(ClipboardKind.IMAGE, "image/png")


def test_non_png_image_type_is_still_chosen_as_image() -> None:
    available = ["image/jpeg", "text/plain"]
    assert choose_read_type(available) == ClipboardChoice(ClipboardKind.IMAGE, "image/jpeg")


def test_uri_list_used_when_no_portal_file_type_present() -> None:
    """A non-GTK source (e.g. a plain X11/XWayland app) may offer uri-list with no portal type."""
    available = ["text/uri-list", "text/plain"]
    assert choose_read_type(available) == ClipboardChoice(ClipboardKind.URI_LIST, "text/uri-list")


def test_plain_text_copy_falls_through_to_text() -> None:
    available = ["text/plain;charset=utf-8", "text/plain", "TEXT", "STRING"]
    assert choose_read_type(available) == ClipboardChoice(
        ClipboardKind.TEXT, "text/plain;charset=utf-8"
    )


def test_bare_text_plain_without_charset() -> None:
    available = ["text/plain"]
    assert choose_read_type(available) == ClipboardChoice(ClipboardKind.TEXT, "text/plain")


def test_empty_clipboard_yields_no_choice() -> None:
    assert choose_read_type([]) is None


def test_unrecognised_types_only_yields_no_choice() -> None:
    assert choose_read_type(["application/x-something-unknown"]) is None
