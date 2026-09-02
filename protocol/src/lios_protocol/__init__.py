"""Shared crypto, framing, pairing and wire types used by the relay and every LIOS client.

Kept free of any web-framework import so it stays a plain library dependency for a GTK
application as much as for an ASGI service.
"""

from __future__ import annotations

__version__ = "0.1.0"
