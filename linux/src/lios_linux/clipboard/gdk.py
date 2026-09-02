"""Native `Gdk.Clipboard` access -- the one trigger where it is strictly better than `wl.py`.

An in-window button click carries its own fresh `pointer_info.press_serial`, satisfying both
of mutter's gates (client focus, and a serial newer than the current owner's) with no focus
blip at all -- the clipboard investigation, section 8. From any other trigger
(a GlobalShortcuts activation, a notification click) GDK has no fresh serial to spend and
`set_content()` silently no-ops while still reporting success; those triggers must use
:mod:`wl` instead. Never call the functions here from anything but an in-window button-click
handler.

Untestable in this environment: constructing a `Gdk.Clipboard` needs a live display
connection, which `this machine` (headless) does not have.
"""

from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GObject", "2.0")

from gi.repository import Gdk, GObject  # noqa: E402


def write_text_from_click(text: str) -> None:
    """Set the clipboard to `text`. Call only from an in-window button-click handler."""
    clipboard = Gdk.Display.get_default().get_clipboard()
    clipboard.set_content(Gdk.ContentProvider.new_for_value(GObject.Value(str, text)))


def write_texture_from_click(texture: "Gdk.Texture") -> None:
    """Set the clipboard to an image. Call only from an in-window button-click handler."""
    clipboard = Gdk.Display.get_default().get_clipboard()
    clipboard.set_content(
        Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.Texture, texture))
    )
