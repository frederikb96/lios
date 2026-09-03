"""Writing the system clipboard via native `Gdk.Clipboard`.

Every call site is a handler for an input event the window itself received -- a click on a
history row's Copy button, or its keyboard accelerator -- which is exactly what satisfies
mutter's gate: keyboard focus, and a `wl_display` serial newer than the current owner's. GDK
sources that serial from the key/button press that led here, so `set_content()` genuinely
takes ownership rather than silently no-opping the way it would from a shortcut or notification
trigger with no input event behind it.

Untestable in a headless environment: constructing a `Gdk.Clipboard` needs a live display
connection.
"""

from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GObject", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gdk, GLib, GObject  # noqa: E402


def _clipboard() -> Gdk.Clipboard:
    display = Gdk.Display.get_default()
    if display is None:
        raise RuntimeError("no default Gdk.Display -- no Wayland session to write to")
    return display.get_clipboard()


def write_text(text: str) -> None:
    """Put `text` on the clipboard as a string."""
    # PyGObject accepts a Python type here and translates it to the matching GType itself;
    # PyGObject-stubs types the parameter more narrowly than the real, common idiom.
    value = GObject.Value(str, text)  # type: ignore[arg-type]
    _clipboard().set_content(Gdk.ContentProvider.new_for_value(value))


def write_image_png(data: bytes) -> None:
    """Put `data` (already-encoded PNG bytes) on the clipboard as an image."""
    texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
    value = GObject.Value(Gdk.Texture, texture)  # type: ignore[arg-type]
    _clipboard().set_content(Gdk.ContentProvider.new_for_value(value))
