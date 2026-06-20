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
| Full suite (SQLite) | `make test` | _pending_ | run at each phase boundary |
| Cross-engine (Postgres) | `make test-docker` | _pending_ | final gate |
| Lint | `ruff check app scripts` | _pending_ | |

### Rollback

- Revert code: `git revert <merge-sha>` (no data migration to undo — schema untouched).
- Per-wave: each wave is an atomic commit; `git revert <wave-sha>` backs out one wave.
