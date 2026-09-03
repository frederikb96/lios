"""`HistoryStore.get`/`blob_path` -- re-reading one item by id, e.g. to re-copy it later."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lios_linux.history.models import Direction, HistoryItem, ItemKind
from lios_linux.history.store import HistoryStore


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    return HistoryStore(
        db_path=tmp_path / "history.sqlite3", blobs_dir=tmp_path / "blobs",
        max_items=50, max_age_days=7,
    )


def test_get_returns_the_stored_item(store: HistoryStore) -> None:
    item = HistoryItem(
        id="abc", direction=Direction.INCOMING, kind=ItemKind.TEXT, preview="hi",
        filename=None, content_type=None, size_bytes=2, created_at=datetime.now(UTC),
    )
    store.add(item, blob=b"hi")

    fetched = store.get("abc")

    assert fetched is not None
    assert fetched.id == "abc"
    assert fetched.preview == "hi"


def test_get_returns_none_for_unknown_id(store: HistoryStore) -> None:
    assert store.get("does-not-exist") is None


def test_blob_path_returns_none_for_a_text_item_with_no_blob(store: HistoryStore) -> None:
    item = HistoryItem(
        id="abc", direction=Direction.INCOMING, kind=ItemKind.TEXT, preview="hi",
        filename=None, content_type=None, size_bytes=2, created_at=datetime.now(UTC),
    )
    store.add(item, blob=None)

    assert store.blob_path("abc") is None


def test_has_any_is_false_for_an_empty_store(store: HistoryStore) -> None:
    assert store.has_any() is False


def test_has_any_is_true_once_something_is_added(store: HistoryStore) -> None:
    item = HistoryItem(
        id="abc", direction=Direction.INCOMING, kind=ItemKind.TEXT, preview="hi",
        filename=None, content_type=None, size_bytes=2, created_at=datetime.now(UTC),
    )
    store.add(item, blob=None)

    assert store.has_any() is True


def test_blob_path_returns_the_written_file_for_an_image(store: HistoryStore) -> None:
    item = HistoryItem(
        id="abc", direction=Direction.INCOMING, kind=ItemKind.IMAGE, preview="photo.png",
        filename="photo.png", content_type="image/png", size_bytes=3, created_at=datetime.now(UTC),
    )
    store.add(item, blob=b"png")

    path = store.blob_path("abc")

    assert path is not None
    assert path.read_bytes() == b"png"
