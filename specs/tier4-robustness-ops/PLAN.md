---
slug: tier4-robustness-ops
status: active
owner: Minh Tran
created: 2026-06-17
---

# Tier 4 — Robustness & Ops Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Ship five independent ops improvements — health endpoints, stable OpenAPI operationIds, idempotency on the non-idempotent POST creates, informational rate-limit headers, and soft-delete for trips.

**Architecture:** Each story is self-contained and independently shippable. Reuse proven in-repo patterns: the booking `Idempotency-Key` replay pattern (`_replay` + `get_by_idempotency_key` + UNIQUE partial index), the booking soft-cancel pattern (status/flag column, not row deletion), and the `crud/trip.py` PRAGMA-guarded `ALTER TABLE` migration. operationIds are pinned centrally via FastAPI's `generate_unique_id_function` (one change), not 52 per-route edits.

**Tech Stack:** FastAPI, Pydantic v2, SQLite (stdlib `sqlite3`), pytest + `TestClient`.

---

## 1. Motivation

AGENT_IMPROVEMENTS.md Tier 4 — real-world correctness for agent consumers: retry-safe mutations, stable codegen/MCP names, health probes for retry logic, self-throttle hints, and recoverable trip deletion.

## 2. Non-goals

- **No enforced rate limiting.** `CLAUDE.md` scopes the project as "no rate limiting"; the headers are **informational/static only** (user-authorized waiver, see `ESCALATIONS.md`). No 429s, no counters.
- **No idempotency on PUT/DELETE/cancel.** Those are already idempotent by HTTP/semantics (replace, delete-twice, cancel-twice). Only the non-idempotent POST **creates** (`POST /trips`, `POST /trips/{id}/items`) get an `Idempotency-Key`. A test pins cancel's existing idempotency; no code change there.
- **No batch endpoint** (it doesn't exist yet — out of scope).
- **operationId** is set centrally, not by rewriting every decorator.

## 3. Success Criteria

- `GET /healthz` → 200 liveness; `GET /readyz` → readiness with DB + routing-provider checks.
- Every route in `app.openapi()` has a stable `operationId` equal to its handler function name, all unique.
- Repeating `POST /trips` / `POST /trips/{id}/items` with the same `Idempotency-Key` returns the original resource, creates no duplicate.
- Every response carries `X-RateLimit-Limit` / `-Remaining` / `-Reset`.
- `DELETE /trips/{id}` is soft: the row is kept, the trip 404s on GET and is absent from `GET /trips`, DELETE still returns 204 and is idempotent.
- Full suite green; `ruff check` / `ruff format --check` clean on touched files.

## 4. Execution order & file map (sequential — no parallel waves)

| Story | Lane | Files |
|---|---|---|
| 1 Health | normal | `app/routers/health.py` (new), `app/routers/main.py`, `app/services/booking_service.py`, `tests/test_health.py` |
| 2 operationId | normal | `app/main.py`, `tests/test_operation_ids.py` |
| 3 Idempotency | normal | `app/crud/trip.py`, `app/services/trip_service.py`, `app/routers/trips.py`, `tests/test_trips.py` |
| 4 Rate-limit headers | normal | `app/main.py`, `app/core/config.py`, `tests/test_rate_limit_headers.py` |
| 5 Soft-delete trips | high-risk | `app/crud/trip.py`, `app/services/trip_service.py`, `tests/test_trips.py` |

Stories 2 & 4 both touch `app/main.py`; Stories 3 & 5 both touch `crud/trip.py` + `trip_service.py` + `tests/test_trips.py` — run strictly sequentially (no same-wave parallelism).

---

## Chunk 1 — Story 1: Health endpoints

### Task 1.1 — `BookingService.ping()` (DB readiness probe)

**Files:** Modify `app/services/booking_service.py`; Test `tests/test_health.py` (created in 1.2).

- [ ] **Step 1:** Add a `ping()` method to `BookingService` that runs a trivial query through its repo and returns `True` if the DB is reachable. Add a matching `ping()` to `BookingRepository` in `app/crud/booking.py`:

```python
# app/crud/booking.py — in BookingRepository
def ping(self) -> bool:
    """Return True if the database is reachable (cheap SELECT 1)."""
    with self._connect() as conn:
        conn.execute("SELECT 1")
    return True
```

```python
# app/services/booking_service.py — in BookingService
def ping(self) -> bool:
    """Return True if the booking store is reachable. Used by /readyz."""
    return self._repo.ping()
```

- [ ] **Step 2:** Verify import: `.venv/bin/python -c "from app.services.booking_service import BookingService"` → exit 0.

**Done:** `BookingService(<tmp>).ping()` returns `True`.

### Task 1.2 — `/healthz` + `/readyz` router

**Files:** Create `app/routers/health.py`; Modify `app/routers/main.py`; Test `tests/test_health.py`.

- [ ] **Step 1: Write failing tests** — create `tests/test_health.py`:

```python
"""Tests for the health/readiness endpoints."""

from fastapi.testclient import TestClient


def test_healthz_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz_ready(client: TestClient) -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    # routing provider is "live" when ORS_API_KEY is set, else "fallback"
    assert body["checks"]["routing_provider"] in {"live", "fallback"}
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_health.py -v` → FAIL (404).

- [ ] **Step 3: Implement** — create `app/routers/health.py`:

```python
"""Liveness and readiness probes — separate app health from upstream (ORS)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.schemas.base import AppBaseModel
from app.services.booking_service import BookingService, get_booking_service

router = APIRouter(tags=["health"])

BookingsDep = Annotated[BookingService, Depends(get_booking_service)]


class HealthResponse(AppBaseModel):
    status: str


class ReadyResponse(AppBaseModel):
    status: str
    checks: dict[str, str]


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
def healthz() -> HealthResponse:
    """Liveness: the app process is up. Does not touch dependencies."""
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse, summary="Readiness probe")
def readyz(bookings: BookingsDep) -> ReadyResponse:
    """Readiness: dependencies are usable.

    Reports the database (must be reachable) and the routing provider as a
    separate, non-fatal upstream — routing degrades to an offline estimate
    without an ORS key, so a missing key is "fallback", not "not ready".
    """
    database = "ok" if bookings.ping() else "error"
    routing = "live" if get_settings().routing_provider_enabled else "fallback"
    return ReadyResponse(
        status="ready" if database == "ok" else "not_ready",
        checks={"database": database, "routing_provider": routing},
    )
```

> Match how other routers import the booking dependency: confirm the exact names `get_booking_service` / `BookingService` from `app/services/booking_service.py` (the same ones `app/routers/bookings.py` uses) and mirror them.

Register in `app/routers/main.py` — add `health` to the `from app.routers import (...)` block and include it first (so its Swagger tag leads):

```python
router.include_router(health.router)
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_health.py -v` → PASS.

**Done:** both probes return 200 with the documented bodies; `/readyz` reflects routing-provider config.

---

## Chunk 2 — Story 2: Stable OpenAPI operationIds

### Task 2.1 — Pin operationIds centrally

**Files:** Modify `app/main.py`; Test `tests/test_operation_ids.py`.

- [ ] **Step 1: Write failing test** — create `tests/test_operation_ids.py`:

```python
"""Every route must expose a stable, unique operationId (== handler name)."""

from fastapi.routing import APIRoute

from app.main import create_app


def test_operation_ids_are_handler_names() -> None:
    app = create_app()
    schema = app.openapi()
    handler_names = {
        r.name
        for r in app.routes
        if isinstance(r, APIRoute) and r.include_in_schema
    }
    op_ids = [
        op["operationId"]
        for methods in schema["paths"].values()
        for op in methods.values()
    ]
    # Pinned: each operationId IS a handler function name, not FastAPI's
    # verbose "<name>_<path>_<method>" default.
    assert set(op_ids) <= handler_names, f"unpinned ids: {set(op_ids) - handler_names}"
    # Stable + unique.
    assert len(op_ids) == len(set(op_ids)), "duplicate operationIds"
```

> Why this assertion and not `"__" not in oid`: FastAPI's defaults are mostly single-underscore (`list_airports_airports_get`), so a `__` check would pass even before the fix — useless. Comparing against the set of handler names is the correct discriminator.

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_operation_ids.py -v` → FAIL: the default ids (e.g. `list_airports_airports_get`) are not handler names, so the subset assertion fails.

- [ ] **Step 3: Implement** — in `app/main.py`, set a custom unique-id function on the app so every operationId is its handler's function name. Add near the top:

```python
from fastapi.routing import APIRoute


def _operation_id(route: APIRoute) -> str:
    """Stable operationId = the handler function name (survives refactors)."""
    return route.name
```

Pass it into the `FastAPI(...)` constructor in `create_app`:

```python
    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.app_version,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
        **docs_kwargs,
    )
```

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_operation_ids.py -v`. The subset assertion now passes, but the **uniqueness** assertion FAILS on a known collision: `list_cities` is the handler name in **both** `app/routers/cities.py` (`GET /cities`) and `app/routers/places.py` (`GET /places/cities`). Resolve it by renaming the **places** handler function `list_cities` → `list_place_cities` (function name only — the route path `/places/cities` is set in the decorator and does **not** change). Re-run → PASS. (Confirmed this is the only in-schema collision among the 42 routes; if the test surfaces another, rename the less-central handler the same way.)

**Done:** all operationIds are the handler names, unique, stable; `list_place_cities` rename applied.

---

## Chunk 3 — Story 3: Idempotency on POST creates

> Mirrors `crud/booking.py` exactly: an `idempotency_key` column + UNIQUE partial index, a `get_*_by_idempotency_key` lookup, an INSERT that returns the race winner on `IntegrityError`, and a service-layer replay check. Applied to `POST /trips` and `POST /trips/{id}/items`.

### Task 3.1 — Trips table: idempotency_key columns + migration

**Files:** Modify `app/crud/trip.py`; Test `tests/test_trips.py`.

- [ ] **Step 1:** Add `idempotency_key TEXT` to both `_TRIPS_SCHEMA` and `_ITEMS_SCHEMA` (for fresh DBs), and append `"idempotency_key"` to both `_TRIP_COLUMNS` and `_ITEM_COLUMNS`. Add it to the value tuples — change `_trip_values` / `_item_values` to accept and append the key:

```python
def _trip_values(trip: Trip, idempotency_key: str | None) -> tuple:
    return (
        trip.id, trip.title, trip.city, _iso(trip.start_date), _iso(trip.end_date),
        trip.travelers, trip.notes, _iso(trip.created_at), idempotency_key,
    )
# (and likewise _item_values(item, idempotency_key) appending the key)
```

- [ ] **Step 2:** Extend `init_db` with PRAGMA-guarded migrations (same pattern as the existing `booking_id` migration) for **both** tables, plus UNIQUE partial indexes:

```python
            for table in ("trips", "trip_items"):
                cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                if "idempotency_key" not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN idempotency_key TEXT")
                conn.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{table}_idempotency_key "
                    f"ON {table} (idempotency_key) WHERE idempotency_key IS NOT NULL"
                )
```

- [ ] **Step 3:** Update `create_trip` and `add_item` to accept `idempotency_key: str | None = None`. **Also update their internal call sites** — `create_trip` calls `_trip_values(trip)` and `add_item` calls `_item_values(item)`; these now take the key (`_trip_values(trip, idempotency_key)`), so update the calls or you'll hit a `TypeError`. On `sqlite3.IntegrityError` return the existing row via the new lookups (mirror `BookingRepository.add`). Add lookups:

```python
    def get_trip_by_idempotency_key(self, key: str) -> Trip | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trips WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            items = conn.execute(
                "SELECT * FROM trip_items WHERE trip_id = ?", (row["id"],)
            ).fetchall()
        return _row_to_trip(row, items)

    def get_item_by_idempotency_key(self, key: str) -> TripItem | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trip_items WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return _row_to_item(row) if row is not None else None
```

> Confirm `_row_to_trip` / `_row_to_item` read by column name (they do, via `sqlite3.Row`), so the new column doesn't break them.

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_trips.py -q` → existing trip tests still PASS (no behavior change yet; columns are additive).

**Done:** schema migrates additively; existing trip tests green.

### Task 3.2 — Service replay + router `Idempotency-Key` header

**Files:** Modify `app/services/trip_service.py`, `app/routers/trips.py`; Test `tests/test_trips.py`.

- [ ] **Step 1: Write failing tests** — append to `tests/test_trips.py` (use the existing trip-creation helper/shape in that file; adapt field names to the real `TripCreate`):

```python
def test_create_trip_idempotent(client):
    payload = {"title": "Idem Trip", "travelers": 2}
    h = {"Idempotency-Key": "trip-key-1"}
    first = client.post("/trips", json=payload, headers=h).json()
    second = client.post("/trips", json=payload, headers=h).json()
    assert first["id"] == second["id"]
    assert len(client.get("/trips").json()) >= 1
    ids = [t["id"] for t in client.get("/trips").json()]
    assert ids.count(first["id"]) == 1  # no duplicate


def test_add_item_idempotent(client):
    trip = client.post("/trips", json={"title": "T", "travelers": 1}).json()
    item = {"day": 1, "kind": "note", "title": "X"}
    h = {"Idempotency-Key": "item-key-1"}
    first = client.post(f"/trips/{trip['id']}/items", json=item, headers=h).json()
    second = client.post(f"/trips/{trip['id']}/items", json=item, headers=h).json()
    assert first["id"] == second["id"]
```

> Before writing, read the existing `tests/test_trips.py` create-trip / add-item tests and match their exact request bodies (field names like `order` vs `sort_order`, required fields). Adjust the payloads above to match.

- [ ] **Step 2:** Run those two tests → FAIL (duplicates created / `add_item` has no key param).

- [ ] **Step 3: Implement** — thread `idempotency_key` through the service, mirroring `BookingService._replay`:

```python
# trip_service.py — create_trip
def create_trip(self, request, idempotency_key: str | None = None) -> Trip:
    if idempotency_key:
        existing = self._repo.get_trip_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing
    # ... existing build logic ...
    return self._repo.create_trip(trip, idempotency_key=idempotency_key)
```

Do the same for `add_item` (replay via `get_item_by_idempotency_key`, pass key into `self._repo.add_item(...)`). Then add the `Idempotency-Key` Header param to the `POST /trips` and `POST /trips/{id}/items` routes in `app/routers/trips.py`, copying the exact `Annotated[str | None, Header(alias="Idempotency-Key", description=..., examples=[...])] = None` block from `app/routers/flights.py:book_flight`, and pass it into the service call.

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_trips.py -q` → PASS.

**Done:** repeated POST with the same key returns the original trip/item, no duplicate; key omitted ⇒ unchanged behavior.

---

## Chunk 4 — Story 4: Informational rate-limit headers

### Task 4.1 — Attach `X-RateLimit-*` headers

**Files:** Modify `app/core/config.py`, `app/main.py`; Test `tests/test_rate_limit_headers.py`.

- [ ] **Step 1: Write failing test** — create `tests/test_rate_limit_headers.py`:

```python
"""Every response advertises informational (unenforced) rate-limit headers."""

from fastapi.testclient import TestClient


def test_rate_limit_headers_present(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.headers["X-RateLimit-Limit"].isdigit()
    assert resp.headers["X-RateLimit-Remaining"].isdigit()
    assert resp.headers["X-RateLimit-Reset"].isdigit()
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_rate_limit_headers.py -v` → FAIL (KeyError).

- [ ] **Step 3: Implement** — add a nominal setting to `app/core/config.py` (`Settings`):

```python
    # Informational only — NOT enforced (see CLAUDE.md "no rate limiting").
    # Advertised so agents can self-throttle.
    rate_limit_nominal: int = 1000
```

In `app/main.py`, set the three headers in the existing `_log_requests` middleware (reuse it — don't add a second middleware), after `response = await call_next(request)`:

```python
        limit = settings.rate_limit_nominal
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
```

> `settings` is already in scope in `create_app`; the middleware closes over it. Use `int(time.time()) + 60` for `Reset` — a plausible Unix epoch (RFC-6585 style), **not** `time.perf_counter()` (which is an arbitrary monotonic reference and would yield a nonsense small number). `time` is already imported in `app/main.py`.

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_rate_limit_headers.py -v` → PASS.

**Done:** all responses carry the three headers; nothing is enforced.

---

## Chunk 5 — Story 5: Soft-delete trips

> **High-risk story** — changes `DELETE /trips/{id}` semantics. Rollback recorded below.

### Task 5.1 — `deleted_at` column + soft-delete CRUD

**Files:** Modify `app/crud/trip.py`; Test `tests/test_trips.py`.

- [ ] **Step 1:** Add `deleted_at TEXT` to `_TRIPS_SCHEMA` and a PRAGMA-guarded migration in `init_db` (same loop/pattern as Task 3.2):

```python
            trip_cols = {row[1] for row in conn.execute("PRAGMA table_info(trips)")}
            if "deleted_at" not in trip_cols:
                conn.execute("ALTER TABLE trips ADD COLUMN deleted_at TEXT")
```

- [ ] **Step 2:** Change `delete_trip` from hard delete to soft (keep items; set the timestamp). Filter it out everywhere a trip is read:

```python
    def delete_trip(self, trip_id: str, *, when: str) -> bool:
        """Soft-delete: stamp deleted_at, keep the row. True if it existed and was live."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE trips SET deleted_at = ? "
                "WHERE id = ? AND deleted_at IS NULL",
                (when, trip_id),
            )
            return cursor.rowcount > 0
```

Add `AND deleted_at IS NULL` (or `WHERE deleted_at IS NULL`) to the `SELECT` in `get_trip` and `list_trips`:
- `list_trips`: `"SELECT * FROM trips WHERE deleted_at IS NULL ORDER BY created_at DESC"`
- `get_trip`: add `AND deleted_at IS NULL` to its WHERE.

> Confirm the exact current `get_trip` SQL in `crud/trip.py` and append the predicate without breaking parameter order.

- [ ] **Step 3: Update the existing crud-level test that asserts hard-delete.** `tests/test_trips.py::test_repo_delete_trip_cascades_items` (line ~95) calls `repo.delete_trip("t1")` (no `when`) and asserts `repo.get_item("i0") is None` — both break under soft-delete. Update it to the soft-delete contract: pass `when=` (e.g. `repo.delete_trip("t1", when="2026-06-17T00:00:00+00:00")`), assert `repo.get_trip("t1") is None` (filtered out), and assert the item **is retained** (`repo.get_item("i0") is not None`). Rename it to `test_repo_soft_delete_trip` to reflect the new behavior.

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_trips.py -q` → adjust the service caller in Task 5.2 if the `when` signature change breaks `test_service_delete_trip`; expect remaining FAILs until 5.2.

**Done:** column migrates; soft-delete CRUD + read filters in place; the stale hard-delete crud test is updated.

### Task 5.2 — Service wiring + behavior tests

**Files:** Modify `app/services/trip_service.py`; Test `tests/test_trips.py`.

- [ ] **Step 1: Write failing tests** — append to `tests/test_trips.py`:

```python
def test_delete_trip_is_soft(client):
    trip = client.post("/trips", json={"title": "Doomed", "travelers": 1}).json()
    assert client.delete(f"/trips/{trip['id']}").status_code == 204
    # Gone from reads…
    assert client.get(f"/trips/{trip['id']}").status_code == 404
    assert trip["id"] not in [t["id"] for t in client.get("/trips").json()]
    # …but delete is idempotent (already-deleted → still 404, no 500)
    assert client.delete(f"/trips/{trip['id']}").status_code == 404
```

- [ ] **Step 2:** Run → FAIL (currently hard-deletes; after 5.1 the signature needs `when`).

- [ ] **Step 3: Implement** — update `TripService.delete_trip` to pass a UTC timestamp and 404 when nothing live matched:

```python
from datetime import datetime, timezone

def delete_trip(self, trip_id: str) -> None:
    self.get_trip(trip_id)  # raises NotFoundError (already filters deleted)
    self._repo.delete_trip(trip_id, when=datetime.now(timezone.utc).isoformat())
    logger.info("Soft-deleted trip %s", trip_id)
```

Since `get_trip` now filters `deleted_at IS NULL`, a second delete raises `NotFoundError` → 404 (idempotent at the API). Keep the route returning 204.

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_trips.py -q` then the full suite `.venv/bin/python -m pytest tests/ -q` → PASS, no regressions (esp. trip value-layer + day-plan tests that read trips).

**Done:** DELETE is soft, GET/list exclude deleted, delete idempotent, data retained.

---

## 5. Risks

- **Migrations on existing `travel.db`:** all three new columns use PRAGMA-guarded `ALTER TABLE ADD COLUMN` (nullable, no default) — safe and idempotent, matching the shipped `booking_id` migration. Tests use a fresh temp DB so they exercise the `CREATE TABLE` path; the migration path is covered by the guard's no-op on fresh tables.
- **Soft-delete read-filter completeness:** every trip read must filter `deleted_at IS NULL`, or deleted trips leak. Task 5.1 enumerates `get_trip` + `list_trips`; the full-suite run in 5.2 Step 4 guards trip value-layer / day-plan readers.
- **operationId collisions:** the central function uses handler names; the 2.1 test fails loudly on any duplicate so it can't ship silently.
- **Rate-limit headers vs policy:** informational only, user-waived (ESCALATIONS.md). No enforcement path is added.

## 6. Rollback (Story 5 — high-risk)

- Revert code: `git revert <story-5-sha>`.
- The `deleted_at` column is additive and nullable — no down-migration needed; reverting the code restores hard-delete behavior. Existing soft-deleted rows would simply become visible again (acceptable; no data lost).

## 7. Status Log

- 2026-06-17 — Plan drafted (status: proposed). New initiative, all 5 items, rate-limit waiver granted (see SUMMARY.md / ESCALATIONS.md).
- 2026-06-17 — Executed via subagent-driven-development on `feat/tier4-robustness-ops` (off v2). Per-story spec+quality reviews ✅.
  - S1 health `68927ca` · S2 operationId `00fde46` · S3 idempotency `375c115` (+ cross-trip fix `1ff0fea`) · S4 rate-limit `5607c76` · S5 soft-delete `f8b2a64`
  - Final correctness review found 2 cross-story bugs (idempotency+soft-delete 500; /readyz 500-on-DB-down) → fixed `2c89787`. Intent review ✅. 570 tests pass.
