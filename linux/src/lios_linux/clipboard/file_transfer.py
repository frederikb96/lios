"""Turning `application/vnd.portal.filetransfer` bytes into `Gio.File`s usable in the sandbox.

GTK4 registers a deserializer for this mime type that does the whole document-portal
round-trip itself (`RetrieveFiles`) and hands back files under `/run/user/<uid>/doc/...` that
are readable even though this application's only filesystem permission is
`--filesystem=xdg-download`. Reading the portal type explicitly -- rather than letting GDK
infer a `GdkFileList` type from whichever mime types the clipboard happens to offer -- avoids a
documented ambiguity between `text/uri-list` and the portal type when both are present on the
same clipboard entry (report 5b69b919-ed12-4092-8de0-1237b5c8b143, section 6).

🚨 Unverified against a live GNOME session: `gdk_content_deserialize_finish`'s exact PyGObject
return shape (a `GObject.Value` to unbox, or the already-unboxed `Gdk.FileList`) could not be
confirmed from here -- `pai-vm` has no display and no working search result settled it either.
Check this against a real GNOME session before shipping; the fallback if it is wrong is a
one-line change to how `_on_finish` below unwraps its result.

Untestable in this environment: deserialization goes through the document portal over D-Bus,
which needs a running desktop session.
"""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gdk, Gio, GLib  # noqa: E402

#: The two portal file-list mime types GTK4 has a deserializer for -- see
#: `lios_linux.clipboard.priority` for which one is preferred and why both exist.
PORTAL_FILE_TRANSFER = "application/vnd.portal.filetransfer"
PORTAL_FILES_LEGACY = "application/vnd.portal.files"


def deserialize_file_list(
    data: bytes,
    mime_type: str,
    *,
    on_done: Callable[[list[Gio.File], Exception | None], None],
) -> None:
    """Turn portal file-list bytes into `Gio.File`s, asynchronously via the GLib main loop.

    `on_done` is invoked exactly once, from the main loop, with either a non-empty result and
    no exception or an empty list and the exception -- never both populated.
    """
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))

    def _on_finish(source: Gio.InputStream, result: Gio.AsyncResult) -> None:
        try:
            value = Gdk.content_deserialize_finish(result)
        except GLib.Error as exc:
            on_done([], exc)
            return
        file_list = value.get_boxed() if hasattr(value, "get_boxed") else value
        on_done(list(file_list.get_files()), None)

    Gdk.content_deserialize_async(
        stream,
        len(data),
        mime_type,
        Gdk.FileList.__gtype__,
        GLib.PRIORITY_DEFAULT,
        None,
        _on_finish,
    )
