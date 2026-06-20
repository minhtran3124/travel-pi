# SUMMARY — DI / Session Refactor

**Lane:** high-risk
**Confidence:** high
**Reason:** Large blast radius (all of `app/crud/`, every `app/services/*`, several
routers, `tests/conftest.py`) but **no DB schema change and no public API contract
change** — purely internal wiring. Direction is unambiguous (target stated in the
architecture review, #1). High confidence because the end-state is idiomatic FastAPI
DI and every wave is independently test-gated.

## Goal

Replace import-time service/repo singletons (bound to `get_settings().database_url`)
with a single request-scoped `get_session()` dependency + unit-of-work, so:
1. services/repos resolve their session via `Depends`, not module globals;
2. multi-step writes share one transaction (atomic);
3. tests override **one** dependency instead of repointing ~13 module globals.

## Hard gates checked

- Auth / authz: not touched.
- DB schema / migration: **not touched** (no model or Alembic change).
- Public contract (routes, request/response shapes): **not touched**.
- Session/transaction scope change: **YES** — request-scoped session + UoW. This is
  the intended change; reviewed per Rule-4 (`auto-correct-scope.md`). Rollback below.

## Rationale

The import-time binding is the root of the documented testing friction
(`trip-service-booking-singleton-test-isolation` memory; `conftest.py:76–110`). A
`get_session` seam fixes testability (P1) and write-atomicity (P3) together.

## Alternatives considered

- **Lazy per-call factory resolution** (re-read settings each call): fixes test
  repointing cheaply but gives no UoW and leaves the global-mutation pattern. Rejected
  — doesn't address P3.
- **Leave stateful services as-is, only migrate reads:** halves the work but bookings
  (the only mutable state) keep per-method sessions → no atomic writes. Rejected.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Full suite (SQLite) | `pytest -q` | 0 | 680 passed after waves 1–3 (was 672 baseline + 8 new) |
| Cross-engine (Postgres) | `make test-docker` | _pending_ | final gate (wave 5) |
| Lint | `ruff check app tests` | 0 | clean after waves 1–3 |

### Deviations

- **Rule 1 (UoW correctness)** — added `begin_nested()` savepoints to `crud/booking.py`
  `add()` and `crud/trip.py` `create_trip`/`add_item`. Their catch-IntegrityError-then-
  requery dedup pattern needs the shared session left usable after a failed flush. Beyond
  task 3.1's listed `<files>` but required for the dual-mode bridge to be UoW-safe.
- **PLAN gap (wave boundary)** — removing the write-service singletons broke two read-side
  callers that reach them outside DI: `place_service.resolve()` (called only by trip_service →
  now takes `session`) and `dashboard.py` `bookings_page` (now `Depends(get_session)`). Tests
  can only override DI, so both had to migrate in wave 3, not wave 4. Folded in.
- **Rule 3 (test migration)** — `test_trip_value_layer_service.py` patch target
  `trip_service.get_booking_service` → `trip_service.BookingService`; `test_trip_budget.py`
  dropped the now-unnecessary `_booking_service` singleton repoint (trip + booking share the
  request session); `svc`/`booking_service` fixtures + conftest rewired to one `get_session`
  override.
- **Harness friction** — the `ruff-on-edit` hook runs `ruff check --fix` and stripped imports
  added *before* their usage existed (masked by no import-time error). Had to re-add. For
  waves 4–5: add import + usage in a single edit, and run `ruff check --select F821` before tests.
- **Follow-up** — `tests/db/_capture_golden.py` (uncollected helper) still uses the old
  `BookingService(url)` signature; not in the suite, fix when next touched.

### Rollback

- Revert code: `git revert <merge-sha>` (no data migration to undo — schema untouched).
- Per-wave: each wave is an atomic commit; `git revert <wave-sha>` backs out one wave.
