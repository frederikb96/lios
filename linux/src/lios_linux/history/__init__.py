"""Local history: the last 50 items over 7 days, in the Flatpak's own data directory.

SQLite for metadata, a sibling `blobs/` directory for image and file payloads. Expiry runs on
a schedule and unlinks any blob whose row is gone, so nothing accumulates on disk beyond what
the retention policy allows -- see :mod:`store` for the mechanics.
"""

from __future__ import annotations
