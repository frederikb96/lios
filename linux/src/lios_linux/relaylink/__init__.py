"""The relay connection: REST calls plus the long-lived `/api/stream` WebSocket.

Built on `libsoup3` (`Soup.Session`), already in `org.gnome.Platform` -- it integrates with the
GLib main loop the GTK app is already running, so there is no second event loop and no
asyncio/GLib bridge. See :mod:`client` for the connection itself, :mod:`backoff` for the
reconnect schedule, :mod:`endpoints` for the pure URL/header building, and :mod:`pairing_flow`
for turning a scanned QR payload (or a freshly generated one) into a paired device.
"""

from __future__ import annotations
