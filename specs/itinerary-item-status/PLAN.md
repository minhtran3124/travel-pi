---
slug: itinerary-item-status
status: shipped
base_branch: v2
feature_branch: feat/itinerary-item-status
---

# Itinerary Item Status (A3) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Give each trip itinerary item a `status` (`pending | booked | constraint | optional`) so an agent can express soft vs. hard plan and hard constraints.

**Architecture:** One new string enum (`TripItemStatus`) added to the central `app/enums.py`, surfaced as an additive `status` field on the `TripItem*` schemas (default `pending`). Persisted as a new `trip_items.status` column added via the shared `ensure_column` helper with `TEXT NOT NULL DEFAULT 'pending'` (so legacy rows backfill on ALTER). Because `DayPlanItem.item` already wraps the whole `TripItem`, the day-plan surfaces `status` for free; the only behavioral service change is gap-detection no longer counting `optional` items as "planned".

**Tech Stack:** Python 3.10+ / FastAPI / Pydantic v2 / raw `sqlite3`, pytest. Phase A migration convention: additive `ensure_column` + a legacy-DB ALTER-path test.

**Spec:** `specs/itinerary-item-status/SUMMARY.md` (intent verbatim, risk flags, hard-gate waiver, assumptions). Checklist source: `specs/agent-platform-roadmap/CHECKLIST.md` A3.

**Run context:** worktree `.claude/worktrees/itinerary-item-status` on branch `feat/itinerary-item-status` (off `v2`). Use the root venv interpreter:
`PYBIN=/Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python`
Baseline before any change: **594 passed**.

**Key assumptions (from SUMMARY):**
1. `status` lives on `TripItemCreate` (settable at create/update, default `pending`) → flows through create/update/read uniformly.
2. Gap-detection's "Day N has no planned items" excludes `optional` items: a day containing *only* optional items is still flagged as a gap.
3. `booked` is an itinerary planning state, independent of `BookingStatus` / `booking_id` (the transactional booking lifecycle). No coupling.

---

## Chunk 1: Enum, schema, persistence, migration test, gap-detection

### Task 1: `TripItemStatus` enum

**Files:**
- Modify: `app/enums.py` (append a new enum next to `TripItemKind`)
- Test: `tests/test_trips.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_trips.py` (top-level, near the other schema tests):

```python
def test_trip_item_status_enum_values():
    from app.enums import TripItemStatus

    assert {s.value for s in TripItemStatus} == {
        "pending",
        "booked",
        "constraint",
        "optional",
    }
    # str-Enum: compares equal to the raw string (JSON/query/store parity)
    assert TripItemStatus.PENDING == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYBIN -m pytest tests/test_trips.py::test_trip_item_status_enum_values -v`
Expected: FAIL — `ImportError: cannot import name 'TripItemStatus'`.

- [ ] **Step 3: Write minimal implementation**

In `app/enums.py`, immediately after the `TripItemKind` class, add:

```python
class TripItemStatus(str, Enum):
    """Planning state of a trip itinerary item.

    Lets an agent express soft vs. hard plan and hard constraints:
    ``pending`` (default, not yet decided), ``booked`` (locked in — note this
    is the *planning* state and is independent of ``BookingStatus`` /
    ``booking_id``), ``constraint`` (a fixed must-happen anchor), and
    ``optional`` (nice-to-have; excluded from gap-detection).
    """

    PENDING = "pending"
    BOOKED = "booked"
    CONSTRAINT = "constraint"
    OPTIONAL = "optional"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYBIN -m pytest tests/test_trips.py::test_trip_item_status_enum_values -v`
Expected: PASS.

---

### Task 2: `status` field on the `TripItem*` schemas

**Files:**
- Modify: `app/schemas/trip.py` (import on line 14; add field to `TripItemCreate`, lines 20-52)
- Test: `tests/test_trips.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_trips.py`:

```python
def test_trip_item_create_default_status_is_pending():
    item = TripItemCreate(day=1, kind="place", title="Marble Mountains")
    from app.enums import TripItemStatus

    assert item.status == TripItemStatus.PENDING


def test_trip_item_create_accepts_each_status():
    for value in ("pending", "booked", "constraint", "optional"):
        item = TripItemCreate(day=1, kind="place", title="x", status=value)
        assert item.status == value


def test_trip_item_create_rejects_bad_status():
    with pytest.raises(ValidationError):
        TripItemCreate(day=1, kind="place", title="x", status="maybe")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYBIN -m pytest tests/test_trips.py -k status -v`
Expected: FAIL — `TripItemCreate` has no `status` (default test errors; bad-status test does not raise).

- [ ] **Step 3: Write minimal implementation**

In `app/schemas/trip.py`, line 14, extend the enum import:

```python
from app.enums import ActivityLevel, MealStyle, TripItemKind, TripItemStatus
```

In `TripItemCreate`, add the field after `kind` (keep it near `kind` so the contract reads logically):

```python
    status: TripItemStatus = Field(
        default=TripItemStatus.PENDING,
        description=(
            "Planning state: pending (default), booked, constraint, or optional. "
            "Optional items are excluded from itinerary gap-detection."
        ),
        examples=["pending"],
    )
```

(`TripItemUpdate` and `TripItem` inherit `TripItemCreate`, so they pick up `status` automatically — no edits needed there.)

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYBIN -m pytest tests/test_trips.py -k status -v`
Expected: PASS (all three).

---

### Task 3: Persist `status` — DDL, columns, row mapping, INSERT/UPDATE, migration

**Files:**
- Modify: `app/crud/trip.py`
  - `_ITEMS_SCHEMA` (lines 32-46) — add column to fresh-table DDL
  - `_ITEM_COLUMNS` (lines 70-82) — add `"status"`
  - `_row_to_item` (lines 90-102) — read `status`
  - `_item_values` (lines 136-149) — write `item.status.value`
  - `init_db` (lines 168-201) — `ensure_column` migration for legacy DBs
  - `update_item` (lines 346-363) — add `status = ?` to the UPDATE
- Test: `tests/test_trips.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_trips.py` (uses the existing `repo` fixture, cf. `test_repo_add_update_delete_item`):

```python
def test_repo_persists_item_status_roundtrip(repo):
    from app.enums import TripItemStatus
    from app.schemas.trip import Trip, TripItem

    trip = Trip(id="t-status", title="Status trip", travelers=1)
    item = TripItem(
        id="i-1",
        trip_id="t-status",
        day=1,
        sort_order=0,
        kind="place",
        title="Anchor",
        status=TripItemStatus.CONSTRAINT,
    )
    repo.create_trip(trip)
    repo.add_item(item)

    got = repo.get_item("i-1")
    assert got.status == TripItemStatus.CONSTRAINT

    got.status = TripItemStatus.OPTIONAL
    assert repo.update_item(got) is True
    assert repo.get_item("i-1").status == TripItemStatus.OPTIONAL


def test_repo_item_defaults_status_pending_when_unset(repo):
    from app.enums import TripItemStatus
    from app.schemas.trip import Trip, TripItem

    trip = Trip(id="t-def", title="Default trip", travelers=1)
    repo.create_trip(trip)
    repo.add_item(
        TripItem(id="i-2", trip_id="t-def", day=1, sort_order=0, kind="note", title="x")
    )
    assert repo.get_item("i-2").status == TripItemStatus.PENDING
```

> Note: confirm the exact add-item method name on `TripRepository` (`add_item` vs `_insert_item`/`create_item`) by reading the class before writing — match `test_repo_add_update_delete_item` at `tests/test_trips.py:104`. Use the same call it uses.

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYBIN -m pytest tests/test_trips.py -k "item_status_roundtrip or defaults_status" -v`
Expected: FAIL — `sqlite3.OperationalError: no column named status` (or `KeyError: 'status'` in `_row_to_item`).

- [ ] **Step 3: Write minimal implementation**

In `_ITEMS_SCHEMA`, add the column (after `idempotency_key`, keep the trailing-comma layout valid):

```python
_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS trip_items (
    id              TEXT PRIMARY KEY,
    trip_id         TEXT NOT NULL,
    day             INTEGER NOT NULL,
    sort_order      INTEGER NOT NULL,
    kind            TEXT NOT NULL,
    title           TEXT NOT NULL,
    place_id        TEXT,
    booking_id      TEXT,
    start_time      TEXT,
    notes           TEXT,
    idempotency_key TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
)
"""
```

In `_ITEM_COLUMNS`, append `"status"` as the last entry:

```python
_ITEM_COLUMNS = (
    "id",
    "trip_id",
    "day",
    "sort_order",
    "kind",
    "title",
    "place_id",
    "booking_id",
    "start_time",
    "notes",
    "idempotency_key",
    "status",
)
```

In `_row_to_item`, add the field (TripItem coerces the raw string into the enum):

```python
        notes=row["notes"],
        status=row["status"],
    )
```

In `_item_values`, append the value (order MUST match `_ITEM_COLUMNS`; `idempotency_key` stays second-to-last, `status` last):

```python
def _item_values(item: TripItem, idempotency_key: str | None) -> tuple:
    return (
        item.id,
        item.trip_id,
        item.day,
        item.sort_order,
        item.kind.value,
        item.title,
        item.place_id,
        item.booking_id,
        item.start_time,
        item.notes,
        idempotency_key,
        item.status.value,
    )
```

In `init_db`, add the migration alongside the existing `ensure_column` calls (after the `deleted_at` line, ~line 201):

```python
            # Add deleted_at to legacy trips tables (soft-delete tombstone).
            ensure_column(conn, "trips", "deleted_at")
            # Add status to legacy trip_items tables (A3). NOT NULL + default
            # backfills pre-existing rows to 'pending'.
            ensure_column(
                conn, "trip_items", "status", "TEXT NOT NULL DEFAULT 'pending'"
            )
```

In `update_item`, add `status = ?` to the SET clause and the value to the params tuple:

```python
    def update_item(self, item: TripItem) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE trip_items SET day = ?, sort_order = ?, kind = ?, "
                "title = ?, place_id = ?, booking_id = ?, start_time = ?, "
                "notes = ?, status = ? WHERE id = ?",
                (
                    item.day,
                    item.sort_order,
                    item.kind.value,
                    item.title,
                    item.place_id,
                    item.booking_id,
                    item.start_time,
                    item.notes,
                    item.status.value,
                    item.id,
                ),
            )
            return cursor.rowcount > 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYBIN -m pytest tests/test_trips.py -k "item_status_roundtrip or defaults_status" -v`
Expected: PASS.

---

### Task 4: Legacy-DB ALTER-path test (Phase A convention)

**Files:**
- Test: `tests/test_trips.py` (or `tests/test_migrations.py` — place it where the other legacy-DB migration tests live; A0 put the helper-level one in `test_migrations.py`, so a `trip_items`-specific one belongs with the trip repo tests).

This proves a DB created **before** the `status` column gains it on `init_db()` with old rows backfilled to `pending` — the A0-mandated obligation for every Phase A schema change.

- [ ] **Step 1: Write the failing test**

```python
def test_init_db_adds_status_to_legacy_trip_items(tmp_path):
    """A trip_items table predating the status column gains it, old rows = pending."""
    import sqlite3

    from app.crud.trip import TripRepository
    from app.enums import TripItemStatus

    db = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db)
    # Legacy schema: trip_items WITHOUT the status column, one existing row.
    conn.execute(
        "CREATE TABLE trip_items ("
        " id TEXT PRIMARY KEY, trip_id TEXT NOT NULL, day INTEGER NOT NULL,"
        " sort_order INTEGER NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,"
        " place_id TEXT, booking_id TEXT, start_time TEXT, notes TEXT,"
        " idempotency_key TEXT)"
    )
    conn.execute(
        "INSERT INTO trip_items (id, trip_id, day, sort_order, kind, title)"
        " VALUES ('old-1', 't-old', 1, 0, 'place', 'Pre-existing')"
    )
    conn.commit()
    conn.close()

    # Migration runs here.
    TripRepository(db).init_db()

    repo = TripRepository(db)
    migrated = repo.get_item("old-1")
    assert migrated.status == TripItemStatus.PENDING

    cols = set()
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(trip_items)")}
    conn.close()
    assert "status" in cols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYBIN -m pytest tests/test_trips.py::test_init_db_adds_status_to_legacy_trip_items -v`
Expected: FAIL only if the migration line from Task 3 is absent. After Task 3 it should already PASS — that's fine; the value here is locking the legacy-DB contract. If Task 3 is implemented, confirm it PASSES and that removing the Task-3 migration line makes it FAIL (sanity check that the test actually exercises the migration).

- [ ] **Step 3: Implementation**

Already done in Task 3 (the `ensure_column(conn, "trip_items", "status", ...)` line). No new code.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYBIN -m pytest tests/test_trips.py::test_init_db_adds_status_to_legacy_trip_items -v`
Expected: PASS.

---

### Task 5: Gap-detection excludes `optional`; day-plan surfaces status

**Files:**
- Modify: `app/services/trip_service.py`
  - import (top of file) — add `TripItemStatus`
  - `get_trip_detail` gap loop (line 305) — exclude `optional` from "planned items"
- Test: `tests/test_trips.py` (gap test via service/`client`) + a day-plan status assertion.

**Why no day-plan serialization change:** `DayPlanItem.item` already embeds the full `TripItem` (`trip_service.py:397-403`), so `status` appears in `GET /trips/{id}/day-plan` automatically once it is on the schema. We only add an assertion proving it.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_trips.py`. Use the `svc` fixture (cf. `test_service_*` tests). Confirm the item-add method name on the service before writing (match an existing `test_service_*` test):

```python
def test_gap_detection_treats_optional_as_unplanned(svc):
    """A day whose only item is optional is still flagged 'no planned items'."""
    from app.enums import TripItemStatus
    from app.schemas.trip import TripCreate, TripItemCreate

    trip = svc.create_trip(
        TripCreate(
            title="Gap trip",
            start_date="2026-07-01",
            end_date="2026-07-01",  # single day
            items=[
                TripItemCreate(
                    day=1, kind="place", title="Maybe-museum",
                    status=TripItemStatus.OPTIONAL,
                )
            ],
        )
    )
    detail = svc.get_trip_detail(trip.id)
    assert any("Day 1 has no planned items" in g for g in detail.gaps)


def test_gap_detection_counts_non_optional_item(svc):
    """A day with a pending item is NOT flagged 'no planned items'."""
    from app.schemas.trip import TripCreate, TripItemCreate

    trip = svc.create_trip(
        TripCreate(
            title="Planned trip",
            start_date="2026-07-01",
            end_date="2026-07-01",
            items=[TripItemCreate(day=1, kind="place", title="Confirmed stop")],
        )
    )
    detail = svc.get_trip_detail(trip.id)
    assert not any("Day 1 has no planned items" in g for g in detail.gaps)
```

> Confirm `TripCreate` accepts `items=[...]` and that `svc.create_trip` takes a `TripCreate` — match `test_service_create_returns_trip_with_ids` at `tests/test_trips.py:133`. If the service signature differs, adapt the call (e.g. create the trip then add items) without changing the assertion.

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYBIN -m pytest tests/test_trips.py -k "gap_detection" -v`
Expected: `test_gap_detection_treats_optional_as_unplanned` FAILS (the optional item currently counts as planned, so no gap is reported); the second test passes already.

- [ ] **Step 3: Write minimal implementation**

In `app/services/trip_service.py`, add `TripItemStatus` to the existing `app.enums` import (find the line importing `BookingStatus`/`BookingType`/`MealStyle` etc. and add `TripItemStatus`).

In `get_trip_detail`, change the gap-loop day-items filter (currently `trip_service.py:305`):

```python
            for day_num in range(1, num_days + 1):
                # Optional items are "nice-to-have" — they don't count as
                # planning a day, so a day with only optional items still
                # reports the no-items gap.
                day_items = [
                    i
                    for i in trip.items
                    if i.day == day_num and i.status != TripItemStatus.OPTIONAL
                ]
                if not day_items:
                    gaps.append(f"Day {day_num} has no planned items.")
                    continue
```

> Leave the `has_hotel` check below it unchanged — it iterates `day_items`, which is now the non-optional set, which is the desired behavior (an optional-only day already gapped out above via `continue`).

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYBIN -m pytest tests/test_trips.py -k "gap_detection" -v`
Expected: PASS (both).

- [ ] **Step 5: Day-plan surfaces status (assertion only)**

Add an endpoint test confirming `status` rides through the day-plan. **Best mirror:** `tests/test_trip_value_layer_api.py` already has copy-pasteable `_create_trip` / `_add_item` helpers (lines ~18-31) and `test_day_plan_returns_200_with_correct_day` (line ~80) showing the exact `resp.json()["items"][n]["item"][...]` access shape and the `?date=` call. **Place the new test there** (not `test_trips.py`) and reuse those helpers. Route confirmed: `GET /trips/{trip_id}/day-plan?date=YYYY-MM-DD` (router `app/routers/trips.py:105-122`, query param `date`):

```python
def test_day_plan_includes_item_status(client):
    # Create a trip with a start_date, add a constraint item on day 1, fetch day-plan.
    # (Match the trip/item creation helpers already used in this file.)
    trip_id = ...  # create via the same helper the other endpoint tests use
    client.post(
        f"/trips/{trip_id}/items",
        json={"day": 1, "kind": "place", "title": "Fixed tour", "status": "constraint"},
    )
    resp = client.get(f"/trips/{trip_id}/day-plan", params={"date": "<trip start_date>"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(pi["item"]["status"] == "constraint" for pi in items)
```

> This test is "fill-in-the-blanks" against the file's existing endpoint helpers — read `test_item_crud_via_endpoints` and any existing day-plan endpoint test first and mirror their exact trip-creation + route usage. If a day-plan endpoint test already exists, extend it instead of duplicating setup.

Run: `$PYBIN -m pytest tests/test_trips.py -k "day_plan_includes_item_status" -v`
Expected: PASS.

---

## Final verification (run after all tasks)

- [ ] **Full suite green (no regressions):**

Run: `$PYBIN -m pytest tests/ -q`
Expected: `60X passed` — was 594; +~9 new tests, **0 failures**. Investigate ANY pre-existing test that now fails (e.g. a snapshot of the `TripItem` shape, an OpenAPI/schema test, or a day-plan fixture) — an additive field with a default should not break them, but the FE-codegen contract test is the most likely tripwire.

- [ ] **Lint + format:**

Run: `ruff check app tests && ruff format --check app tests`
Expected: clean on touched files. (`flight.py` has known pre-existing drift — do not "fix" unrelated files.)

- [ ] **Manual contract sanity (optional):** start `uvicorn app.main:app --port 8000` and confirm `/docs` shows `status` on `TripItemCreate`/`TripItem` with enum `pending|booked|constraint|optional`.

## Status Log

- 2026-06-18 — shipped via `feat/itinerary-item-status` (PR #7 → v2). All review gates ✅; full suite 604 passed.

## Downstream (NOT in this plan)

- Update `specs/itinerary-item-status/SUMMARY.md` → `### Verify` table with real exit codes at DONE.
- Mark A3 ✅ in `specs/agent-platform-roadmap/CHECKLIST.md` (progress line + Status Log) — Phase B gate opens once A3 merges to `v2`.
- PR targets **`v2`** (not main), `gh` under the `minhtran3124` account.
- Review chain before PR: spec + quality + `/correctness-review` + `/intent-review` (per subagent-driven-development).
