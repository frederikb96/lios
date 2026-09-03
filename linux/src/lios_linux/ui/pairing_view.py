"""Displaying the pairing invite -- the QR code and the underlying pairing link, both built
from the same URI `lios_protocol.pairing.encode_qr_uri` produces.

The QR code is rendered by drawing the module matrix directly with Cairo rather than through
`qrcode`'s default Pillow-based image factory, so this application does not need Pillow as a
dependency just to show one QR code.

Untestable in this environment: needs a live display connection.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

import cairo  # noqa: E402
import qrcode  # noqa: E402
from gi.repository import Gtk  # noqa: E402

from lios_linux.clipboard import gdk  # noqa: E402

#: Shown next to the copy button. The pairing link carries the fleet's whole group key in
#: the clear, and that key has no expiry and no rotation mechanism anywhere in this codebase --
#: a leak through this text or the clipboard history it lands in is a permanent compromise
#: until every device is wiped and the fleet is paired again from scratch.
_EXPOSURE_WARNING = (
    "Anyone who reads this text, or the clipboard history it lands in, can read everything "
    "sent as this device until the whole fleet is re-paired -- this link's key never expires "
    "and cannot be rotated."
)


class QrCodeWidget(Gtk.DrawingArea):
    """A square `Gtk.DrawingArea` rendering one QR code for `uri`."""

    def __init__(self, uri: str, *, size: int = 300) -> None:
        super().__init__()
        qr = qrcode.QRCode(border=2)
        qr.add_data(uri)
        qr.make(fit=True)
        self._matrix = qr.get_matrix()
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_draw_func(self._draw)

    def _draw(self, _area: Gtk.DrawingArea, cr: cairo.Context, width: int, height: int) -> None:
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.set_source_rgb(0, 0, 0)
        side = len(self._matrix)
        cell = min(width, height) / side
        for row_index, row in enumerate(self._matrix):
            for col_index, is_dark in enumerate(row):
                if is_dark:
                    cr.rectangle(col_index * cell, row_index * cell, cell, cell)
        cr.fill()


class PairingInviteView(Gtk.Box):
    """The QR code alongside the same pairing link as selectable text, with a copy button.

    A device rejoining the fleet with no camera to scan the QR -- or reading it off another
    device's screen from across the room -- has this text to type or copy instead. The copy
    button writes directly to the system clipboard: it runs inside this widget's own window
    in response to the button press that triggered it, which is what a native `Gdk.Clipboard`
    write on GNOME Wayland requires (see `lios_linux.clipboard`).
    """

    def __init__(self, uri: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        self.append(QrCodeWidget(uri))

        entry = Gtk.Entry(text=uri, editable=False, hexpand=True)
        entry.set_alignment(0.0)

        copy_button = Gtk.Button(icon_name="edit-copy-symbolic")
        copy_button.set_tooltip_text("Copy pairing link")
        copy_button.connect("clicked", lambda _button: gdk.write_text(uri))

        link_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        link_row.append(entry)
        link_row.append(copy_button)
        self.append(link_row)

        warning = Gtk.Label(label=_EXPOSURE_WARNING, wrap=True, xalign=0.0)
        warning.add_css_class("dim-label")
        warning.set_max_width_chars(40)
        self.append(warning)
