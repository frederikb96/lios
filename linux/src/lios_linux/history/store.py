"""SQLite-backed history with a sibling blob directory and explicit, testable expiry.

Two independent limits, both enforced by :meth:`HistoryStore.expire`: an item older than
`max_age_days` is gone regardless of how few items exist; the newest `max_items` survive
regardless of age. An item dismissed without saving is still findable until either limit
catches it -- there is no other way for an item to disappear.

Nothing is unlinked lazily. `expire` is the only place a blob file is deleted, and it always
deletes the blob together with the row that referenced it -- never one without the other. It
is meant to run at startup and on a periodic timer, both driven by the application, not by
this module.

Also holds the one piece of state that must outlive the process entirely: the relay-side
catch-up watermark (`get_catch_up_since`/`advance_catch_up_since`), a single row kept apart
from the `items` table on purpose. An item's own `created_at` column is this device's local
processing time -- fine for local retention, wrong for a relay query, since a clock-skewed
local clock could set a watermark ahead of the relay's own idea of "now" and cause the next
catch-up to skip something. The watermark only ever advances from `ItemSummary.created_at`,
the relay's own authoritative timestamp.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lios_linux.history.models import Direction, HistoryItem, ItemKind

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    direction TEXT NOT NULL,
    kind TEXT NOT NULL,
    preview TEXT NOT NULL,
    filename TEXT,
    content_type TEXT,
    size_bytes INTEGER NOT NULL,
    created_at REAL NOT NULL,
    blob_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_created_at ON items (created_at);

CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 0),
    catch_up_since REAL NOT NULL
);
"""


class HistoryStore:
    """One SQLite file plus one blob directory, both created on first use if missing."""

    def __init__(
        self, *, db_path: Path, blobs_dir: Path, max_items: int, max_age_days: int
    ) -> None:
        """
        Args:
            db_path: path to the SQLite database file.
            blobs_dir: directory image/file payloads are written to, one file per item id.
            max_items: how many of the newest items `expire` keeps.
            max_age_days: how many days an item survives regardless of the item cap.
        """
        self._db_path = db_path
        self._blobs_dir = blobs_dir
        self._max_items = max_items
        self._max_age_days = max_age_days
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._blobs_dir.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def add(self, item: HistoryItem, *, blob: bytes | None) -> Path | None:
        """Insert one row, writing `blob` to the blob directory if given.

        Returns the blob's path, or `None` for a text item with nothing to write -- its
        preview already holds everything in the row.
        """
        blob_path: Path | None = None
        if blob is not None:
            blob_path = self._blobs_dir / item.id
            blob_path.write_bytes(blob)

        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO items "
                "(id, direction, kind, preview, filename, content_type, size_bytes, "
                " created_at, blob_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.direction.value,
                    item.kind.value,
                    item.preview,
                    item.filename,
                    item.content_type,
                    item.size_bytes,
                    item.created_at.timestamp(),
                    str(blob_path) if blob_path is not None else None,
                ),
            )
            conn.commit()
        return blob_path

    def get(self, item_id: str) -> HistoryItem | None:
        """One row by id, or `None` if it has expired or never existed."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, direction, kind, preview, filename, content_type, size_bytes, "
                "created_at FROM items WHERE id = ?",
                (item_id,),
            ).fetchone()
        if row is None:
            return None
        return HistoryItem(
            id=row[0],
            direction=Direction(row[1]),
            kind=ItemKind(row[2]),
            preview=row[3],
            filename=row[4],
            content_type=row[5],
            size_bytes=row[6],
            created_at=datetime.fromtimestamp(row[7], tz=UTC),
        )

    def blob_path(self, item_id: str) -> Path | None:
        """The blob file for `item_id`, or `None` for a text item or an unknown id."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT blob_path FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return Path(row[0])

    def list_recent(self) -> list[HistoryItem]:
        """Every row currently stored, newest first. Does not itself apply any limit."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, direction, kind, preview, filename, content_type, size_bytes, "
                "created_at FROM items ORDER BY created_at DESC"
            ).fetchall()
        return [
            HistoryItem(
                id=row[0],
                direction=Direction(row[1]),
                kind=ItemKind(row[2]),
                preview=row[3],
                filename=row[4],
                content_type=row[5],
                size_bytes=row[6],
                created_at=datetime.fromtimestamp(row[7], tz=UTC),
            )
            for row in rows
        ]

    def has_any(self) -> bool:
        """Whether any row currently exists -- cheaper than `list_recent()` when the caller
        only needs to know whether history is empty, not its contents."""
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT 1 FROM items LIMIT 1").fetchone()
        return row is not None

    def get_catch_up_since(self) -> datetime | None:
        """The relay timestamp of the newest item this device has successfully received,
        persisted across restarts -- the watermark the next `/api/stream` catch-up resumes
        from. `None` if nothing has ever been received (a fresh pairing, or a device that
        has only ever sent), in which case the caller falls back to "now": there is nothing
        to catch up on, and a brand-new device should not retroactively pull the fleet's
        whole retained history.
        """
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT catch_up_since FROM sync_state WHERE id = 0").fetchone()
        if row is None:
            return None
        return datetime.fromtimestamp(row[0], tz=UTC)

    def advance_catch_up_since(self, when: datetime) -> None:
        """Move the watermark forward to `when` if it is newer than what is already stored.

        Never backward: items can arrive out of the relay's own creation order (a slow
        upload retried after a faster, later one already landed), and regressing the
        watermark would make the next catch-up re-list things already handled.
        """
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO sync_state (id, catch_up_since) VALUES (0, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "catch_up_since = MAX(catch_up_since, excluded.catch_up_since)",
                (when.timestamp(),),
            )
            conn.commit()

    def update_limits(self, *, max_items: int, max_age_days: int) -> None:
        """Change the retention limits `expire` enforces from now on -- e.g. after the user
        edits them in preferences. Takes effect on the next `expire` call, not retroactively."""
        self._max_items = max_items
        self._max_age_days = max_age_days

    def expire(self, *, now: datetime) -> None:
        """Delete rows older than the retention window, then trim to the newest `max_items`.

        Every deleted row's blob file is unlinked in the same pass, so a crash between the two
        never leaves an orphan on one side only within a single call.
        """
        cutoff = (now - timedelta(days=self._max_age_days)).timestamp()
        with closing(self._connect()) as conn:
            self._delete_where(conn, "created_at < ?", (cutoff,))

            surplus_ids = conn.execute(
                "SELECT id FROM items ORDER BY created_at DESC LIMIT -1 OFFSET ?",
                (self._max_items,),
            ).fetchall()
            if surplus_ids:
                placeholders = ",".join("?" for _ in surplus_ids)
                self._delete_where(
                    conn, f"id IN ({placeholders})", tuple(row[0] for row in surplus_ids)
                )
            conn.commit()

    def _delete_where(
        self, conn: sqlite3.Connection, where_clause: str, params: tuple[object, ...]
    ) -> None:
        """Unlink the blob of, then delete, every row matching `where_clause`."""
        rows = conn.execute(
            f"SELECT id, blob_path FROM items WHERE {where_clause}", params  # noqa: S608
        ).fetchall()
        for _row_id, blob_path in rows:
            if blob_path is not None:
                Path(blob_path).unlink(missing_ok=True)
        conn.execute(f"DELETE FROM items WHERE {where_clause}", params)  # noqa: S608
