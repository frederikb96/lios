"""History retention: last 50 items, 7 days, nothing left behind (the design).

An item dismissed without saving must still be findable for the retention window, and gone
without a trace -- including its blob file -- once it ages out or falls past the item cap.
Exercises the real SQLite file and a real blob directory under `tmp_path`, not mocks, so the
unlink-the-orphan behaviour is genuinely proven rather than assumed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lios_linux.history.models import Direction, HistoryItem, ItemKind
from lios_linux.history.store import HistoryStore


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(
        db_path=tmp_path / "history.sqlite3",
        blobs_dir=tmp_path / "blobs",
        max_items=50,
        max_age_days=7,
    )


def _make_item(
    *, created_at: datetime, kind: ItemKind = ItemKind.TEXT, blob: bytes | None = None
) -> HistoryItem:
    return HistoryItem(
        id=f"item-{created_at.timestamp()}",
        direction=Direction.INCOMING,
        kind=kind,
        preview="hello",
        filename=None,
        content_type=None,
        size_bytes=len(blob) if blob else 5,
        created_at=created_at,
    )


def test_item_within_retention_is_still_findable(store: HistoryStore) -> None:
    now = datetime.now(UTC)
    store.add(_make_item(created_at=now), blob=None)

    store.expire(now=now + timedelta(days=6, hours=23))

    assert len(store.list_recent()) == 1


def test_item_past_seven_days_is_expired_and_removed(store: HistoryStore) -> None:
    now = datetime.now(UTC)
    store.add(_make_item(created_at=now), blob=None)

    store.expire(now=now + timedelta(days=7, hours=1))

    assert store.list_recent() == []


def test_expiry_unlinks_the_orphaned_blob_file(store: HistoryStore) -> None:
    now = datetime.now(UTC)
    item = _make_item(created_at=now, kind=ItemKind.IMAGE, blob=b"png-bytes")
    blob_path = store.add(item, blob=b"png-bytes")

    assert blob_path is not None
    assert blob_path.exists()

    store.expire(now=now + timedelta(days=8))

    assert not blob_path.exists()


def test_item_beyond_the_fiftieth_newest_is_trimmed(store: HistoryStore) -> None:
    now = datetime.now(UTC)
    # 51 items, all well within the 7-day window, oldest first.
    for i in range(51):
        store.add(_make_item(created_at=now + timedelta(seconds=i)), blob=None)

    store.expire(now=now + timedelta(seconds=51))

    remaining = store.list_recent()
    assert len(remaining) == 50
    # The single oldest item (second 0) is the one trimmed; the newest (second 50) survives.
    assert all(item.id != "item-" + str((now).timestamp()) for item in remaining)
    assert any(item.id == f"item-{(now + timedelta(seconds=50)).timestamp()}" for item in remaining)


def test_trimming_unlinks_the_trimmed_items_blob(store: HistoryStore) -> None:
    now = datetime.now(UTC)
    oldest = _make_item(created_at=now, kind=ItemKind.IMAGE, blob=b"a")
    oldest_blob_path = store.add(oldest, blob=b"a")
    for i in range(1, 51):
        store.add(_make_item(created_at=now + timedelta(seconds=i)), blob=None)

    store.expire(now=now + timedelta(seconds=51))

    assert oldest_blob_path is not None
    assert not oldest_blob_path.exists()


def test_expire_runs_cleanly_with_an_empty_store(store: HistoryStore) -> None:
    store.expire(now=datetime.now(UTC))
    assert store.list_recent() == []


def test_list_recent_orders_newest_first(store: HistoryStore) -> None:
    now = datetime.now(UTC)
    store.add(_make_item(created_at=now), blob=None)
    store.add(_make_item(created_at=now + timedelta(seconds=1)), blob=None)

    recent = store.list_recent()
    assert recent[0].created_at > recent[1].created_at
