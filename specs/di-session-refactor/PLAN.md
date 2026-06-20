---
slug: di-session-refactor
status: active
owner: Minh Tran
created: 2026-06-20
---

# DI / Session Refactor — request-scoped session + unit-of-work

Implements recommendation **#1** from `specs/architecture-review/REVIEW.md` (fixes
**P1** import-time singletons and **P3** no unit-of-work).

## 1. Motivation

Every service binds the DB URL at **import time**
(`booking_service.py:335`, `tip_service.py:42`, … 13 module globals total) and exposes
either a `get_*_service()` Depends-getter (3 stateful write services) or a
`set_*_repo()` global mutator (~10 read modules + `dashboard`/`cities` routers). The
cost:

- **Testability (P1):** `tests/conftest.py:76–110` must repoint ~13 globals by hand;
  every new service adds another line. Documented footgun
  (`trip-service-booking-singleton-test-isolation` memory).
- **Write atomicity (P3):** each repo method opens its own `with self._sf() as s:`
  (`crud/booking.py`), so a request that calls several repo methods spans multiple
  transactions — multi-step booking/trip writes are not atomic.

Target end-state (idiomatic FastAPI): one request-scoped `get_session()` dependency;
repos take a live `Session`; services/routers resolve via `Depends`; tests override
**one** dependency.

## 2. Non-goals

- No DB **schema** change, no Alembic migration, no model edits.
- No **public API contract** change (route paths, methods, request/response shapes
  stay byte-identical — verified by the existing route/operation-id tests).
- Not fixing P2 (`HTTPException` in routers), P4 (CI), or any other review item — those
  are separate plans.
- No async DB engine — stays sync-on-threadpool per `engine.py`.

## 3. Success Criteria

1. `app/db/session.py` exposes `get_session()` (request-scoped, commit-on-success /
   rollback-on-exception / close) and is the single seam tests override.
2. Zero `set_*_repo()` setters and zero module-level repo/service singletons remain in
   `app/services/` and `app/routers/` (guard test greps for them).
3. `tests/conftest.py` repointing block collapses to a single
   `app.dependency_overrides[get_session] = ...`.
4. A new test proves a multi-step write rolls back atomically on mid-request failure.
5. `make test` and `make test-docker` both green; `ruff check app scripts` clean.
6. No diff in `GET /openapi.json` operation set vs `main` (contract unchanged).

## 4. Tasks

### Task 1.1 — Request-scoped session dependency + UoW

```xml
<task id="1.1" wave="1">
  <files>app/db/session.py, tests/db/test_session.py</files>
  <action>Add get_session() generator dependency in app/db/session.py: resolve get_session_factory(get_settings().database_url), open one Session, `yield` it, commit() on clean exit, rollback() on exception, close in finally. Keep get_session_factory untouched. No existing file edited. Add unit tests: commit-on-success, rollback-on-exception, session closed after.</action>
  <verify>pytest tests/db/test_session.py -x</verify>
  <done>get_session yields a request-scoped Session with commit/rollback/close semantics; tests pass; no other file changed.</done>
</task>
```

### Task 2.1 — Repo dual-mode bridge (enabler, keeps everything green)

```xml
<task id="2.1" wave="2">
  <files>app/crud/booking.py, app/crud/trip.py, app/crud/saved_place.py, app/crud/flight.py, app/crud/airline.py, app/crud/airport.py, app/crud/city.py, app/crud/country.py, app/crud/fx.py, app/crud/hotel_ref.py, app/crud/place_ref.py, app/crud/tip.py, app/crud/visa.py, tests/crud/test_repo_dual_mode.py</files>
  <action>Give every repo a `_session()` contextmanager bridge so it accepts EITHER a live Session OR a sessionmaker. In __init__: if arg is a Session, store self._s (caller-managed, do NOT close); else store self._sf (legacy self-managed). Replace each method's `with self._sf() as s:` with `with self._session() as s:`. This is backward-compatible — all current callers pass a factory and keep working. Factor the bridge once (helper or tiny base mixin) to avoid 13x duplication. No consumer/service edits in this wave.</action>
  <verify>pytest tests/crud -x && make test</verify>
  <done>Repos work with both a Session and a sessionmaker; full suite still green (no behavior change yet).</done>
</task>
```

### Task 3.1 — Migrate stateful write services to get_session + UoW

```xml
<task id="3.1" wave="3">
  <files>app/services/booking_service.py, app/services/trip_service.py, app/services/saved_place_service.py, app/routers/bookings.py, app/routers/trips.py, app/routers/health.py, tests/conftest.py, tests/services/test_uow_atomicity.py</files>
  <action>Convert BookingService/TripService/SavedPlaceService so get_booking_service/get_trip_service/get_saved_place_service take `session: Session = Depends(get_session)` and build the service from a Session-bound repo (drop the import-time `_*_service = X(get_settings().database_url)` globals). Preserve init_db() for lifespan/bootstrap via a classmethod that takes a factory. Routers already use the Depends-getters — keep their Annotated deps, only the getter impl changes. Update conftest: replace the three `dependency_overrides[get_*_service]` lines with one `dependency_overrides[get_session]` yielding a session on the temp DB; remove the saved_place_service._saved_place_service mutation. Add test_uow_atomicity: a multi-step write that raises mid-request leaves the DB unchanged (rollback).</action>
  <verify>pytest tests/api/booking tests/api/trip tests/services/test_uow_atomicity.py -x</verify>
  <done>Write services resolve via get_session; multi-step writes are atomic; no import-time service singleton remains in the 3 modules.</done>
</task>
```

> **Cross-service note for Phase 4:** `booking_service` calls `flight_service` +
> `hotel_service`; `place_service` calls `saved_place_service`; `destination_service`
> calls `weather_service` (no DB). Migration contract: **every migrated read service
> exposes functions that accept `session: Session`** (or a session-bound repo). When a
> write service calls a read service it passes its own request session. Each Phase-4
> task therefore also edits its callers — those caller files are listed in the task's
> `<files>` so same-wave tasks stay file-disjoint.

### Task 4.1 — Migrate flight + hotel reads (called by booking)

```xml
<task id="4.1" wave="4">
  <files>app/services/flight_service.py, app/services/hotel_service.py, app/routers/flights.py, app/routers/hotels.py, app/services/booking_service.py, tests/conftest.py</files>
  <action>Replace flight_service/hotel_service module-global repos + set_*_repo setters with Session-injected providers (Depends(get_session)). flight_service also drops _index_repo/_airline_repo globals. Update booking_service call-sites to pass the request session into flight/hotel lookups. Update flights.py/hotels.py routers to inject. Remove the flight/hotel lines from conftest's repointing block.</action>
  <verify>pytest tests/api/flight tests/api/hotel tests/api/booking -x</verify>
  <done>flight/hotel reads resolve via get_session; booking still resolves flights/hotels using the shared request session; no flight/hotel globals or setters remain.</done>
</task>
```

### Task 4.2 — Migrate place + saved-place read path

```xml
<task id="4.2" wave="4">
  <files>app/services/place_service.py, app/routers/places.py, tests/api/place/test_places.py</files>
  <action>Replace place_service module-global _place_repo + setter with a Session-injected provider. place_service.resolve() reaches saved places — pass the request session into the saved-place lookup (saved_place was migrated in 3.1). Update places.py router to inject. Remove place lines from conftest.</action>
  <verify>pytest tests/api/place -x</verify>
  <done>place reads + saved-place shortlisting resolve via get_session; no place globals/setters remain.</done>
</task>
```

### Task 4.3 — Migrate tip + visa reads (each uses tip/visa + city + country repos)

```xml
<task id="4.3" wave="4">
  <files>app/services/tip_service.py, app/services/visa_service.py, app/routers/tips.py, app/routers/visa.py, tests/api/tip/test_tips.py, tests/api/visa/test_visa.py</files>
  <action>Replace tip_service (tip/city/country) and visa_service (visa/city/country) module globals + setters with Session-injected providers. Update tips.py/visa.py routers to inject. Remove tip/visa lines from conftest.</action>
  <verify>pytest tests/api/tip tests/api/visa -x</verify>
  <done>tip/visa reads resolve via get_session; no tip/visa globals/setters remain.</done>
</task>
```

### Task 4.4 — Migrate currency + airport + destination + routing + board reads

```xml
<task id="4.4" wave="4">
  <files>app/services/currency_service.py, app/services/airport_service.py, app/services/destination_service.py, app/services/routing_service.py, app/services/board_service.py, app/routers/currency.py, app/routers/airports.py, app/routers/destinations.py, tests/api/currency/test_currency.py, tests/api/airport/test_airports.py</files>
  <action>Replace remaining read-service module globals + setters (fx, airport, city in destination/routing, airline in board) with Session-injected providers. destination_service stays async but takes the city repo via the request session; weather_service is unchanged (no DB). Update the listed routers to inject. Remove these services' lines from conftest.</action>
  <verify>pytest tests/api/currency tests/api/airport tests/api/destination tests/api/route -x</verify>
  <done>currency/airport/destination/routing/board reads resolve via get_session; no globals/setters remain in these modules.</done>
</task>
```

### Task 4.5 — Migrate cities + dashboard routers (own repo globals)

```xml
<task id="4.5" wave="4">
  <files>app/routers/cities.py, app/routers/dashboard.py, tests/api/city/test_cities.py</files>
  <action>Replace cities_router.set_city_repo and dashboard_router.set_repos(...) global-mutation wiring with Session-injected providers (Depends(get_session)) inside these routers. Remove the cities/dashboard lines from conftest.</action>
  <verify>pytest tests/api/city tests/api/dashboard -x</verify>
  <done>cities + dashboard resolve repos via get_session; no router-level repo globals/setters remain.</done>
</task>
```

### Task 5.1 — Remove the dual-mode shim, add guards, full cross-engine gate

```xml
<task id="5.1" wave="5">
  <files>app/crud/booking.py, app/crud/trip.py, app/crud/saved_place.py, app/crud/flight.py, app/crud/airline.py, app/crud/airport.py, app/crud/city.py, app/crud/country.py, app/crud/fx.py, app/crud/hotel_ref.py, app/crud/place_ref.py, app/crud/tip.py, app/crud/visa.py, tests/architecture/test_no_singletons.py</files>
  <action>Now that every caller passes a Session, remove the legacy factory branch from the repo `_session()` bridge so repos take only a Session (keep init_db()'s factory path if lifespan still needs it). Add tests/architecture/test_no_singletons.py: grep app/services + app/routers and assert no `set_.*_repo`/module-level `_.*_repo =`/`_.*_service =` survive. Confirm conftest is down to one get_session override.</action>
  <verify>pytest tests/architecture/test_no_singletons.py -x && make test && ruff check app scripts</verify>
  <done>No singletons/setters remain; guard test enforces it going forward; full SQLite suite + lint green.</done>
</task>
```

### Task 5.2 — Cross-engine + contract parity gate

```xml
<task id="5.2" wave="5">
  <files>specs/di-session-refactor/SUMMARY.md</files>
  <action>Run the full Postgres suite and confirm the OpenAPI operation set is unchanged vs main (no public-contract drift). Record results in SUMMARY.md ### Verify (fill exit codes + notes). No code change.</action>
  <verify>make test-docker</verify>
  <done>make test-docker green; openapi operation set identical to main; SUMMARY.md Verify table filled with real exit codes.</done>
</task>
```

## 5. Waves

| Wave | Tasks | Parallelism | Notes |
|------|-------|-------------|-------|
| 1 | 1.1 | single | foundation; touches only new files |
| 2 | 2.1 | single | cross-cutting in `app/crud/`; keeps suite green |
| 3 | 3.1 | single | write services + UoW + conftest collapse begins |
| 4 | 4.1, 4.2, 4.3, 4.4, 4.5 | **5 parallel** | file-disjoint read-service migrations |
| 5 | 5.1, 5.2 | 2 (5.2 after 5.1) | remove shim, guards, cross-engine + contract gate |

Wave-4 file-disjointness verified: 4.1 (flight/hotel + booking), 4.2 (place), 4.3
(tip/visa), 4.4 (currency/airport/destination/routing/board), 4.5 (cities/dashboard)
share no source files. All five edit `tests/conftest.py` — **conftest is the one
shared file**, so either (a) serialize the conftest edits, or (b) have each Phase-4
task leave its conftest lines and do the single conftest collapse in 5.1. **Recommend
(b)** to preserve wave-4 parallelism; adjust 4.x `<files>` to drop `tests/conftest.py`
if taking that route.

## 5b. Wave 4 progress & revised approach

On execution, wave 4's "5 independent parallel groups" proved optimistic: the read
services form a **deep call graph** (destination→hotel/tip/place/weather,
trip→place/routing, board→airport/flight, visa→tip), so they migrate **caller-before-
callee**, not as independent groups. Each service still migrates with the same recipe —
convert to `class(Session)` + `get_X_service` DI provider, inject in its router, drop its
`set_*_repo` + conftest line — and its calls to *still-global* services keep working until
those migrate (then the caller's call site is updated to `XService(self._session)`).

Done & committed (each green, 680 passing):
- `c6c885e` currency (leaf)
- `7b78590` destination (caller; its place/tip/hotel/weather calls remain global)

Remaining: board(+dashboard `set_repos`), visa, routing(async), hotel, tip, place,
airport, flight, weather(async), cities router. Then wave 5 (remove dual-mode shim,
no-singletons guard, `make test-docker`). `dashboard.py` (759 lines, multiple endpoints +
`set_repos`) and the async weather/routing pair are the largest remaining pieces.

**Wave 4 COMPLETE** — finished via 4 parallel subagents (flight/board/airport;
hotel/tip/visa; place/routing/cities; dashboard) on disjoint files, then orchestrator
integration of the shared callers (booking/trip/destination/dashboard) + conftest collapse
+ test fixups. weather_service left as-is (no DB repo). Result: **zero `set_*_repo`/`set_repos`
and zero module-level repo/service singletons remain** in `app/services` + `app/routers`
(verified by grep); 15 `get_*` DI providers; `tests/conftest.py` repointing block fully
removed — a single `get_session` override is the only seam. Verify: `pytest -q` → **680
passed**, ruff + F821 clean. Read-service unit tests now use a `seeded_session` fixture.

## 6. Risks

- **Cross-service session threading** (highest): a write service calling a read service
  must pass its request session, not open a new one — otherwise UoW atomicity breaks
  and you silently get two transactions. Mitigation: the Phase-4 migration contract
  (read services accept `session`); `test_uow_atomicity` (3.1) guards the booking path.
- **Lifespan/seed bootstrap** still needs a factory (no request context at startup):
  keep `init_db()` / `seed_all()` on the factory path; only request handlers use
  `get_session`. Verify startup in `make up` and lifespan tests.
- **conftest shared-file contention** in wave 4 — see Waves note; use approach (b).
- **`expire_on_commit=False`** is already set (`engine.py:40`) so objects survive the
  commit-at-request-end; confirm no handler reads attributes off a committed ORM row
  after return (repos already map to Pydantic before returning — low risk).
- **Dashboard HTML** (`dashboard.py`, 759 lines) is the largest router migration; budget
  extra review there.

## 7. Status Log

- 2026-06-20 — Plan drafted (proposed). Surface mapped: 3 stateful services, ~10
  function-style read modules, 2 routers with repo globals; conftest repointing
  `conftest.py:76–110`.
- 2026-06-20 — ✓ Wave 1 (task 1.1) complete. `app/db/session.py` (`get_session()` +
  UoW) + `tests/db/test_session.py` (3 tests). Verify: `pytest tests/db/test_session.py`
  → 3 passed. New files only; no existing file touched.
- 2026-06-20 — ✓ Wave 2 (task 2.1) complete. Added `app/crud/base.py` (`Repo`
  dual-mode: `_session()`/`_commit()`/`_bind()`); all 13 repos inherit it and dropped
  their redundant `__init__`. Commit semantics: factory mode commits per-op (legacy),
  live-session mode flushes + defers commit. Added `tests/crud/test_repo_dual_mode.py`
  (3 tests). Verify: full suite `pytest -q` → **678 passed**, ruff clean. Backward-
  compatible (no live-session caller yet).
- 2026-06-20 — Branch `refactor/di-session` created off `v3`; waves 1–2 committed `df8795f`.
- 2026-06-20 — ✓ Wave 3 (task 3.1 + folded-in edges) complete. Booking/Trip/SavedPlace
  services take a `Session` (built per request via `Depends(get_session)`); singletons +
  per-service `init_db` methods replaced by module `init_db()` (lifespan calls them).
  trip→booking and trip→place(saved) now share the request session. Savepoints added for
  idempotency under UoW. conftest collapsed to one `get_session` override. Verify:
  `pytest -q` → **680 passed**, ruff clean; new `tests/services/test_uow_atomicity.py`
  proves rollback-on-failure / commit-on-success. See SUMMARY.md Deviations (3 read-side
  edges folded forward from wave 4; savepoints beyond task 3.1 files).
