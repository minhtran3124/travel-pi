# Improvement Plan — Travel Planner Mock API

Derived from the 2026-05-29 architecture review. Items are ordered by priority
and grouped into phases that can each land green (full `pytest` suite passing).

Baseline at start: **366 tests passing**.

---

## Phase 1 — High priority, isolated, low risk

### 1a. Catch-all exception handler (the one real bug)
Only `AppError`, `HTTPException`, and `RequestValidationError` are handled. Any
other uncaught exception escapes as a raw `text/plain` 500, **breaking the
documented JSON-envelope contract** — an agent consuming the API hits a parse
failure instead of a structured error.

- Add `@app.exception_handler(Exception)` in `app/main.py` that logs at
  `ERROR` (with traceback) and returns the standard envelope as a 500
  `{error: "InternalServerError", message, status_code, path, hint}`.
- The message stays generic (no internal detail leak); the traceback goes to
  the log only.
- Add a test in `tests/test_errors.py` mounting a route that raises, asserting
  the 500 envelope shape. (Use a throwaway app/route so the real app is
  untouched.)

### 1b. Documentation truth-up
- `GAP-ANALYSIS.md`: mark `GET /tips`, `GET /places/route`, `GET /cities/route`
  as **implemented** (they ship with ~48 tests). The only still-open item is
  the `trips` group (see Phase 4).
- `CLAUDE.md`: correct the test count (**366**, not 336); clarify that
  lightweight limit/offset pagination **is implemented and in scope**
  (`schemas/pagination.py`); fix the three stale `mock-api-spec.md §1/§9`
  references (point to `APIS.md` / `README.md` / the test suite).

---

## Phase 2 — Request-contract hardening (breaking change, done as one unit)

### 2a. Fix the `guests` field mismatch
`HotelBookingRequest` defines `rooms` / `adults` / `children`, but 18 test
payloads send `guests: N`. It silently "passes" only because the base model
drops unknown fields — the booking actually used the `adults=2` default. Map
each `guests: N` to the correct party fields in `tests/test_bookings.py` and
`tests/test_hotels.py`.

### 2b. Forbid unknown request fields
Add `extra="forbid"` to `AppBaseModel` (`app/schemas/base.py`) so a misspelled
or stale field is a loud 422 instead of a silent drop — the root cause of 2a.
Pydantic v2 merges `model_config` up the MRO, so subclasses that set their own
`model_config` (e.g. `HotelBookingRequest`) still inherit it.

### 2c. Regression test
Add a test asserting that POSTing an unknown field (e.g. `guests`) to
`/hotels/book` now returns 422 with the standard envelope — locking in the fix.

---

## Phase 3 — Persistence & test hygiene (medium)

### 3a. SQLite WAL mode
Set `PRAGMA journal_mode=WAL` (and `synchronous=NORMAL`) in the `_connect()`
helpers of `app/crud/booking.py` and `app/crud/flight.py` to reduce
reader/writer lock contention under FastAPI's sync threadpool.

### 3b. Settings cache isolation
`get_settings` is `@lru_cache`d and `create_app()` is session-scoped, so a
future test that tweaks env vars would silently get stale settings. Add an
autouse fixture (or explicit `cache_clear()`) so config tests are reliable.

---

## Phase 4 — New features ✅ DONE

- **`/trips` itinerary aggregation** ✅ — `schemas/trip.py`, `crud/trip.py`,
  `services/trip_service.py`, `routers/trips.py`, `TripStatus` enum, lifespan
  table init. Endpoints: `POST /trips`, `GET /trips`, `GET /trips/{id}`
  (expanded — resolves bookings + itinerary places), `PATCH /trips/{id}`,
  `DELETE /trips/{id}` (soft cancel). Same SQLite/WAL/idempotency/derived-code
  patterns as bookings; `TripService` takes the `BookingService` as a
  parameter (not the singleton) for test-isolation.
- **`GET /destinations/{city}/overview`** ✅ — `schemas/destination.py`,
  `services/destination_service.py`, `routers/destinations.py`. Pure
  composition over place/tip/hotel/airport/weather services; weather is
  best-effort (`weather: null` on upstream failure), no new storage.
- **End-to-end workflow tests** ✅ — `tests/test_workflows.py`:
  flight search→book→retrieve→cancel, hotel availability→book→ledger, the full
  plan-a-trip journey, and a trip reflecting a cancelled booking.

**Result:** 417 tests pass (was 366 at the start of this work); `ruff check`
clean. `APIS.md`, `CLAUDE.md`, and `GAP-ANALYSIS.md` updated — no open gaps.

---

## Explicitly NOT doing (considered, consciously skipped)
Auth, ORM/migration framework, rate limiting, cursor pagination, DB
VACUUM/retention, env-conditional CORS logic — all out of scope for a minimal
mock backend. Production CORS risk is handled by a doc warning, not code.
