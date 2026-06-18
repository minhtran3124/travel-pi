"""Shared SQLite migration helpers.

Idempotent column/index adds for legacy DBs created before a column existed.
Centralises the ``PRAGMA table_info`` → ``ALTER TABLE ADD COLUMN`` guard that
``crud/trip.py`` and ``crud/booking.py`` previously repeated inline.

Note: table/column names are internal constants (not user input), so the
f-string SQL here carries no injection risk.
"""

import sqlite3


def ensure_column(
    conn: sqlite3.Connection, table: str, column: str, decl: str = "TEXT"
) -> bool:
    """Add ``column`` to ``table`` if absent. Return True iff it was added.

    Idempotent: a no-op (returns False) when the column already exists.
    """
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column in cols:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    return True


def ensure_unique_partial_index(
    conn: sqlite3.Connection, table: str, column: str, name: str | None = None
) -> None:
    """Create a UNIQUE partial index on ``column`` (non-NULL rows only).

    Partial (``WHERE column IS NOT NULL``) so keyless rows aren't forced unique
    on NULL. ``IF NOT EXISTS`` makes it idempotent. Default name ``ix_<t>_<c>``.
    """
    name = name or f"ix_{table}_{column}"
    conn.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {name} "
        f"ON {table} ({column}) WHERE {column} IS NOT NULL"
    )
