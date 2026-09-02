"""Displaying the pairing QR code -- the URI `lios_protocol.pairing.encode_qr_uri` builds.

Rendered by drawing the QR module matrix directly with Cairo rather than through `qrcode`'s
default Pillow-based image factory, so this application does not need Pillow as a dependency
just to show one QR code.

Untestable in this environment: needs a live display connection.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

import cairo  # noqa: E402
import qrcode  # noqa: E402
from gi.repository import Gtk  # noqa: E402


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
