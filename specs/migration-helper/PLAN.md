---
slug: migration-helper
status: shipped
owner: Minh Tran
created: 2026-06-18
---

# A0 — Shared SQLite Migration Helper

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Extract the repeated `PRAGMA table_info` → `ALTER TABLE ADD COLUMN` guard (and the
UNIQUE-partial-index add) into one tested helper module, then refactor the existing call sites —
behavior-identical.

**Architecture:** New `app/crud/_migrations.py` with two pure helpers; `crud/trip.py` and
`crud/booking.py` `init_db()` call them instead of inline PRAGMA/ALTER. No schema change, no new
columns — same additive, idempotent migrations expressed once.

**Tech Stack:** stdlib `sqlite3`, pytest.

---

## 1. Motivation

The `booking_id`, `idempotency_key`, and `deleted_at` migrations each re-implement the same
PRAGMA-guarded `ALTER TABLE ADD COLUMN`. A0 (CHECKLIST.md) makes future Phase A column adds use one
tested path.

## 2. Non-goals

- **No new or destructive migration.** Same columns, same idempotency. (Behavior-preserving — the
  `data-loss/migration` gate is waived for this refactor; see ESCALATIONS.md.)
- No Alembic; no shared repository base class.
- Leave the plain non-unique `confirmation_code` index inline (already one idempotent line; not the
  duplicated pattern).

## 3. Success Criteria

- `app/crud/_migrations.py` exposes `ensure_column` + `ensure_unique_partial_index`.
- `trip.py` + `booking.py` `init_db()` use them; **full suite stays green** (570) — proof the
  refactor is behavior-identical.
- A **legacy-DB test** exercises the ALTER path (column added to a pre-existing table) — the
  elevated-proof obligation from the escalation.
- `ruff` clean.

## 4. Tasks

### Task 1 — Migration helper module + unit tests (TDD)

**Files:**
- Create: `app/crud/_migrations.py`
- Test: `tests/test_migrations.py`

- [ ] **Step 1: Write failing tests** — `tests/test_migrations.py`:

```python
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
    # second call still a no-op, no error
    assert ensure_column(c, "t", "note", "TEXT") is False


def test_ensure_unique_partial_index_allows_multiple_nulls_blocks_dupes():
    c = _conn()
    c.execute("CREATE TABLE t (id TEXT, key TEXT)")
    ensure_unique_partial_index(c, "t", "key")
    ensure_unique_partial_index(c, "t", "key")  # IF NOT EXISTS → idempotent
    c.execute("INSERT INTO t VALUES ('1', NULL)")
    c.execute("INSERT INTO t VALUES ('2', NULL)")  # multiple NULLs allowed
    c.execute("INSERT INTO t VALUES ('3', 'k')")
    import pytest

    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO t VALUES ('4', 'k')")  # duplicate non-null blocked
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_migrations.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement** — `app/crud/_migrations.py`:

```python
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

    Idempotent: a no-op (returns False) when the column already exists, so it
    is safe to call on every startup.
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
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_migrations.py -v` → PASS.

**Done:** helper module + 3 tests green (incl. legacy-DB ALTER path).

### Task 2 — Refactor `init_db` call sites (behavior-preserving)

**Files:**
- Modify: `app/crud/trip.py`, `app/crud/booking.py`

- [ ] **Step 1:** In `app/crud/trip.py`, import the helpers and replace the three inline migrations
  inside `init_db` with calls — keeping identical behavior:

```python
from app.crud._migrations import ensure_column, ensure_unique_partial_index
# ...
            ensure_column(conn, "trip_items", "booking_id")
            for table in ("trips", "trip_items"):
                ensure_column(conn, table, "idempotency_key")
                ensure_unique_partial_index(conn, table, "idempotency_key")
            ensure_column(conn, "trips", "deleted_at")
```

- [ ] **Step 2:** In `app/crud/booking.py` `init_db`, replace the inline `idempotency_key` /
  `confirmation_code` PRAGMA+ALTER guards with `ensure_column(...)`, and the UNIQUE partial index
  with `ensure_unique_partial_index(conn, "bookings", "idempotency_key")`. **Leave** the plain
  non-unique `ix_bookings_confirmation_code` `CREATE INDEX IF NOT EXISTS` line as-is.

- [ ] **Step 3:** Run the full suite — this is the behavior-identical proof:

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 570 passed (no regressions). Pay attention to `tests/test_bookings.py`, `tests/test_trips.py`.

- [ ] **Step 4:** `ruff check app/crud tests/test_migrations.py && ruff format --check app/crud tests/test_migrations.py` → clean.

**Done:** both `init_db`s use the helper; suite green; no behavior change.

## 5. Risks

- **Behavior drift in migrations** — mitigated: helpers reproduce the exact PRAGMA-guard + ALTER +
  partial-index logic; full suite (incl. fresh-DB CREATE path) + the new legacy-DB ALTER test are
  the guard. The final correctness review re-checks the diff.
- **Gate interaction** — the diff moves `ALTER TABLE` lines, tripping `data-loss/migration`. Commit
  with `RISK_WARN_CATEGORIES="data-loss/migration"` (human-authorized waiver; ESCALATIONS.md).

## 6. Rollback

- `git revert <sha>` — additive helper module + inline→call-site swap; reverting restores the
  original inline migrations. No schema/data change either direction.

## 7. Status Log

- 2026-06-18 — Plan drafted (proposed). Normal lane + migration waiver; elevated proof = legacy-DB test.

- 2026-06-18 — shipped via `feat/migration-helper` (PR pending, base `v2`).
