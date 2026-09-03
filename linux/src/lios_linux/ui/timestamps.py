"""Human-friendly rendering of a history item's timestamp.

Pure and GTK-free on purpose -- `history_row.py` needs a live display connection and cannot be
unit-tested here, but the formatting rule itself can be.
"""

from __future__ import annotations

from datetime import datetime, timedelta

_JUST_NOW = timedelta(seconds=30)
_ONE_HOUR = timedelta(hours=1)


def format_timestamp(created_at: datetime, *, now: datetime | None = None) -> str:
    """Local time, relative for anything recent -- most of what someone scans a clipboard
    history for is from the last few minutes, and an absolute time forces them to do the
    UTC-to-local and now-minus-then arithmetic themselves for exactly the items they care
    about most.

    `created_at` is expected timezone-aware (UTC, as everything in this codebase is stored);
    `astimezone()` converts to the system's local timezone with no naive-UTC-as-local mistake.
    """
    local = created_at.astimezone()
    reference = now.astimezone() if now is not None else datetime.now().astimezone()
    delta = reference - local

    if delta < _JUST_NOW:
        return "Just now"
    if delta < _ONE_HOUR:
        minutes = int(delta.total_seconds() // 60)
        return f"{minutes} minute ago" if minutes == 1 else f"{minutes} minutes ago"
    if local.date() == reference.date():
        return local.strftime("%H:%M")
    return local.strftime("%Y-%m-%d %H:%M")
