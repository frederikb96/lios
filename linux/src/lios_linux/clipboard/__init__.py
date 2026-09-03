"""Clipboard access on GNOME Wayland.

GNOME implements no clipboard protocol usable by a background or sandboxed client:
`wlr-data-control`/`ext-data-control` are refused by mutter as deliberate policy, and the
`org.freedesktop.portal.Clipboard` portal only extends RemoteDesktop/InputCapture sessions. A
resident GTK app's own `Gdk.Clipboard` writes natively only from a genuine in-window input
event -- mutter requires both keyboard focus and a `wl_display` serial newer than the current
owner's, and GDK sources that serial only from a key/button press the application actually
received. Every clipboard touch in this application happens inside a window that already has
focus, in response to an input event the app itself received -- Ctrl+V to send, a Copy button
or its accelerator to receive -- so that gate is satisfied honestly and no helper process is
needed.

- :mod:`priority` -- pure, display-free logic: given the mime types the clipboard currently
  offers, which one to act on.
- :mod:`gdk` -- writing the system clipboard via native `Gdk.Clipboard`.

Reading the clipboard for a paste-to-send happens directly in `ui/window.py`, since it is
inherently tied to the widget event that triggered it (an async `Gdk.Clipboard.read_*` call
started from a key handler); see there for the mechanism.
"""

from __future__ import annotations
