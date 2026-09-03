"""`HistoryStore.get_catch_up_since`/`advance_catch_up_since` -- the watermark that survives a
process restart, kept apart from the `items` table's own `created_at` (this device's local
processing time, not the relay's) precisely so a client resuming after downtime asks the relay
for the right thing instead of silently repeating the bug this watermark exists to fix.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lios_linux.history.store import HistoryStore


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(
        db_path=tmp_path / "history.sqlite3", blobs_dir=tmp_path / "blobs",
        max_items=50, max_age_days=7,
    )


def test_a_fresh_store_has_no_watermark(store: HistoryStore) -> None:
    """A device that has never received anything (a fresh pairing) has nothing to report --
    the caller falls back to "now" rather than retroactively pulling the fleet's history."""
    assert store.get_catch_up_since() is None


def test_advancing_sets_the_watermark(store: HistoryStore) -> None:
    when = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    store.advance_catch_up_since(when)
    assert store.get_catch_up_since() == when


def test_advancing_with_an_older_timestamp_does_not_regress_it(store: HistoryStore) -> None:
    """Items can arrive out of the relay's own creation order -- a slow upload retried after
    a faster, later one already landed -- and regressing the watermark would make the next
    catch-up re-list something already handled."""
    newer = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    older = newer - timedelta(hours=1)

    store.advance_catch_up_since(newer)
    store.advance_catch_up_since(older)

    assert store.get_catch_up_since() == newer


def test_advancing_with_a_newer_timestamp_moves_it_forward(store: HistoryStore) -> None:
    first = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    later = first + timedelta(hours=1)

    store.advance_catch_up_since(first)
    store.advance_catch_up_since(later)

    assert store.get_catch_up_since() == later
