"""Clipboard access on GNOME Wayland.

GNOME implements no clipboard protocol usable by a background or sandboxed client:
`wlr-data-control`/`ext-data-control` are refused by mutter as deliberate policy, and the
`org.freedesktop.portal.Clipboard` portal only extends RemoteDesktop/InputCapture sessions. A
resident GTK app's own `Gdk.Clipboard` can write natively only from a genuine in-window input
event (a button click) -- mutter requires both keyboard focus and a `wl_display` serial newer
than the current owner's, and GDK sources that serial only from a key/button press the
application actually received. A portal activation token buys the focus half and not the
serial half, so `set_content()` from a shortcut or notification handler appears to succeed and
silently does nothing.

`wl-copy`/`wl-paste` work unconditionally because they briefly present a transparent surface
and take the fresh `wl_keyboard.enter` serial that comes with it. This package spawns them for
every clipboard touch except the one case where native GDK is strictly better: an in-window
button click, which already carries its own fresh serial and no focus blip.

- :mod:`priority` -- pure, display-free logic: given the mime types the clipboard currently
  offers, which one to act on.
- :mod:`subprocess_runner` -- the reapable-child abstraction `wl.py` spawns through.
- :mod:`wl` -- the `wl-copy`/`wl-paste` backend, used for every headless-triggered touch.
- :mod:`gdk` -- the native `Gdk.Clipboard` path, used only for an in-window button click.
- :mod:`file_transfer` -- turning `application/vnd.portal.filetransfer` bytes into `GFile`s
  readable inside the sandbox.
"""

from __future__ import annotations
