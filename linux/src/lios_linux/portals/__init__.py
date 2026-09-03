"""Thin wrappers over the XDG desktop portals this application uses.

Every portal call here follows the request/response pattern the portal spec defines (see
:mod:`request`), except Notification, which has no request step at all -- it fires directly
and answers, if ever, via `ActionInvoked` on the portal itself.

Untestable in a headless environment: every module needs a running `xdg-desktop-portal` (and,
for Background, a compositor backend for it) on the session bus.
"""

from __future__ import annotations
