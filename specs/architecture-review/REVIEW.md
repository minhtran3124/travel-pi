---
slug: architecture-review
status: complete
owner: Minh Tran
created: 2026-06-20
type: architecture-review
---

# Architecture Review — Travel-PI FastAPI Mock Backend

**Verdict: A-.** This is a genuinely well-architected codebase — the layering
discipline it claims is actually enforced, not aspirational. The weaknesses are a
small number of consistent, fixable patterns rather than structural rot.

> Method: four parallel read-only audits (layering, persistence/seed/migrations,
> API-contract/errors/config/async, testing/DI/ops) plus direct verification of the
> two highest-impact findings (`engine.py`, `booking_service.py`, `crud/booking.py`,
> router sync/async). One audit claim was corrected on verification — see note under
> Strength #5.

---

## What it is

Layered FastAPI backend: `routers → services (rules) → crud (ORM)`. SQLAlchemy 2.0
sync ORM over a URL-selected engine (SQLite local/test, Postgres in Docker), Alembic
migrations, idempotent DB seeding from `app/data/`. Flights & hotel availability are
MD5-seeded deterministic generation (never stored); bookings/trips/saved-places are
the only mutable state. ~21k LOC, 672 tests across all 18 routers.

---

## Strengths (keep these)

1. **Layering is real, not decorative.** No `HTTPException`, `sqlalchemy`, or
   `models.` imports leak into `services/` or `schemas/`. ORM is confined to `crud/`,
   and the repos are genuinely logic-free (`crud/booking.py` only maps rows ↔
   Pydantic). Routers are thin delegators.
2. **Unified error envelope.** `main.py:64–146` normalizes `AppError`,
   `HTTPException`, and `RequestValidationError` into one JSON shape, with services
   raising only domain exceptions (`NotFoundError`/`ConflictError`/`UpstreamError`).
3. **Strong persistence base.** `UUIDBase` with `deterministic_uuid()` (UUID5) makes
   re-seeding idempotent; partial unique indexes on `confirmation_code`/
   `idempotency_key` with both `sqlite_where` and `postgresql_where` show real
   dual-engine care. FKs without ORM `relationship()` → no accidental N+1.
4. **Idempotent, guarded seed pipeline.** `session.merge()` + natural-key upsert for
   `City`; import-time consistency guards (every city ≥3 hotels/places, country
   references valid) fail loudly; `from app.data` is confined to `seed.py`.
5. **Correct async discipline.** Async *only* for real network I/O (`weather_service`,
   `routing_service`), `httpx.AsyncClient` always in `async with`,
   `asyncio.gather(..., return_exceptions=True)` for route legs, graceful degradation
   to haversine/`weather=null`. Sync DB routes run in FastAPI's threadpool by design
   (`engine.py` docstring) — the right call.
   > Correction: an audit flagged sync booking endpoints as "sub-optimal." This is
   > wrong — DB routes are sync `def` (`bookings.py:24,70,93`, `flights.py:32`), which
   > FastAPI runs in a threadpool automatically. `engine.py`'s docstring confirms the
   > intent. Not a defect.
6. **Schemas built for a typed FE.** Discriminated unions (`FlightBookingDetails |
   HotelBookingDetails`), generic `PagedResponse[T]`, validation pushed to the schema
   boundary so bad dates → 422 not a misleading 404.
7. **Broad, isolated tests.** 672 tests, per-run temp SQLite, cross-engine parity via
   `make test-docker`.

---

## Weaknesses & risks (prioritized)

### P1 — Module-level service singletons bind the DB URL at import time
`_booking_service = BookingService(get_settings().database_url)`
(`booking_service.py`), same for trip/saved-place + 11 reference-repo singletons.
Consequence: tests must *mutate global state* — `conftest.py:88–110` repoints all 11
via `set_*_repo()`. Every new service adds conftest boilerplate; there's no clean DI
seam, and this is exactly the footgun the project memory records
(`trip-service-booking-singleton-test-isolation`). **#1 architectural debt.**

### P2 — `HTTPException` leaks back into routers at the validation boundary
`flights.py:111–132`, `hotels.py:182–185`, `places.py:113,118`, `tips.py:64–67`,
`visa.py:47–50` raise `HTTPException(422)` directly — violating the "only `main.py`
does HTTP" invariant the rest of the code respects. Validation is split: some at the
Pydantic boundary, some hand-rolled in routers.

### P3 — No request-scoped session / unit-of-work
Every repo method opens its own `with self._sf() as s:` (`crud/booking.py`). A single
request that calls several repo methods spans multiple sessions/transactions —
multi-step writes aren't atomic. For bookings (the only mutable state) this is a
latent correctness gap, not just style.

### P4 — No CI
Zero `.github/workflows/`. 672 tests + ruff gate exist only as local `.claude/hooks/`
— nothing enforces them on push/PR. The whole quality apparatus is opt-in per machine.

### P5 — Two schema sources of truth
SQLite path uses `create_all` (lifespan), Postgres uses Alembic. They can silently
diverge, and `create_all` won't add columns to an existing DB — already biting the
project (memory: `stale-travel-db-breaks-suite-on-schema-change`). Only 2 migrations
exist for 18 tables.

### P6 — String collation divergence
No explicit `COLLATE` on name/FK comparisons (`City.country`, `Country.name`). SQLite
compares case-insensitively by default, Postgres case-sensitively — a seed casing
mismatch could pass locally and fail (or silently mismatch FKs) on Postgres.

### P7 — Hardcoded data as Python
`app/data/places.py` (4,273 lines) and `hotels.py` (3,497 lines) are ~36% of the
codebase. They bloat diffs/reviews and risk merge pain; this is reference *data*, not
code.

### P8 — Flight-ID coupling is a documented footgun
Flight IDs depend on the exact RNG call order + `Airline.position`. Well-documented,
but any reorder silently invalidates every previously issued ID with no test guarding
the contract.

### Minor
- CORS defaults to `["*"]` (`config.py:98–101`) — fine for dev, not documented as
  dev-only.
- In-process caches (`routing_service._route_cache`, `climate_service._climate_cache`)
  are module-global dicts; safe under single-thread async today, worth a note if ever
  touched from threadpooled sync paths.
- `FlightBookingRequest.passenger_phone` required vs `FlightBookingDetails.
  passenger_phone` optional — undocumented asymmetry.

---

## Recommended improvements (highest leverage first)

1. **Replace singletons with a session dependency + unit-of-work.** Add
   `get_session()` (`Depends`) yielding one request-scoped session; have services take
   the session (or factory) via DI rather than binding the URL at import. Fixes P1 + P3
   together and deletes the conftest repointing dance. *Highest leverage.*
2. **Pull router validation into services/schemas; ban `HTTPException` outside
   `main.py`.** Convert the 5 routers' manual 422s into `DomainValidationError` (or
   Pydantic validators). Add a test that greps `app/routers` + `app/services` for
   `HTTPException`. (Fixes P2.)
3. **Add a GitHub Actions workflow** running `ruff check`, `make test`, and
   `make test-docker`. Logic already exists in the hooks — lift it into CI. (Fixes P4.)
4. **Make Alembic the single schema source of truth.** Drop `create_all` (or gate it to
   a dev-only flag), run `alembic upgrade head` everywhere including tests, and add a
   test asserting `models metadata == migrations head` (autogenerate → no diff). Kills
   P5 and the stale-`travel.db` failures permanently.
5. **Externalize the big data files** to JSON/YAML loaded by `app/data/` (guards stay
   in code). Shrinks ~7.7k lines of `.py` to reviewable data. (Fixes P7.)
6. **Normalize collation:** seed-time guard asserting consistent casing for
   city/country keys, or declare case-insensitive collation explicitly. (Fixes P6.)
7. **Add a flight-ID golden test** pinning known `(origin,dest,date) → flight_id` pairs
   so the load-bearing seed contract fails loudly if the algorithm shifts. (Fixes P8.)

---

## Bottom line

The bones are excellent — disciplined layering, real idempotency, thoughtful
dual-engine handling. The debt clusters in one place (import-time singletons / no DI
seam) that cascades into the documented testing friction, plus a handful of
consistency breaches (router validation, dual schema source) and the missing CI. Fix
#1–#4 and this goes from "well-built mock" to "production-shaped reference backend."

---

## Evidence index (key file:line references)

| Finding | Evidence |
|---|---|
| Layering clean | no `HTTPException`/`sqlalchemy`/`models.` in `services/`,`schemas/`,`routers/` |
| Error envelope | `app/main.py:64–146`, `app/exceptions.py`, `app/schemas/error.py` |
| UUIDBase / det. UUID | `app/db/base.py:67–77` |
| Partial unique indexes | `app/db/models/booking.py:29–38`, `trip.py:27–28` |
| Idempotent seed | `app/db/seed.py` (`session.merge`, City natural-key upsert) |
| Import-time guards | `app/data/places.py`, `hotels.py` (tail), `app/core/invariants.py` |
| Async clients | `app/services/weather_service.py:118`, `routing_service.py:102,264–269` |
| Singletons | `booking_service.py` (`_booking_service`), `trip_service.py`, `saved_place_service.py`; `conftest.py:88–110` |
| HTTPException in routers | `flights.py:111–132`, `hotels.py:182–185`, `places.py:113,118`, `tips.py:64–67`, `visa.py:47–50` |
| Session-per-method | `app/crud/booking.py` (`with self._sf() as s:`) |
| Sync DB on threadpool | `app/db/engine.py` docstring; `bookings.py:24,70,93`, `flights.py:32` |
| Dual schema source | `app/core/lifespan.py:34–35` (`create_all` vs Alembic) |
| Migrations | `alembic/versions/` (2 files, 18 tables) |
| No CI | no `.github/workflows/`; gates in `.claude/hooks/` |
| Big data files | `app/data/places.py` (4273), `hotels.py` (3497) |
| Flight-ID coupling | `app/services/flight_service.py`, `app/crud/flight.py`, `app/db/models/flight_index.py` |
