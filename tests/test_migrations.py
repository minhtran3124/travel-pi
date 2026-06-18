"""Tests for the shared SQLite migration helpers."""

import sqlite3

from app.crud._migrations import ensure_column, ensure_unique_partial_index


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def test_ensure_column_adds_to_legacy_table():
    c = _conn()
    c.execute("CREATE TABLE t (id TEXT)")  # legacy table missing the column
    added = ensure_column(c, "t", "note", "TEXT")
    assert added is True
    cols = {r[1] for r in c.execute("PRAGMA table_info(t)")}
    assert "note" in cols


def test_ensure_column_is_idempotent():
    c = _conn()
    c.execute("CREATE TABLE t (id TEXT, note TEXT)")
    assert ensure_column(c, "t", "note", "TEXT") is False  # already present → no-op
    assert ensure_column(c, "t", "note", "TEXT") is False


def test_ensure_unique_partial_index_allows_multiple_nulls_blocks_dupes():
    import pytest

    c = _conn()
    c.execute("CREATE TABLE t (id TEXT, key TEXT)")
    ensure_unique_partial_index(c, "t", "key")
    ensure_unique_partial_index(c, "t", "key")  # IF NOT EXISTS → idempotent
    c.execute("INSERT INTO t VALUES ('1', NULL)")
    c.execute("INSERT INTO t VALUES ('2', NULL)")  # multiple NULLs allowed
    c.execute("INSERT INTO t VALUES ('3', 'k')")
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO t VALUES ('4', 'k')")  # duplicate non-null blocked
