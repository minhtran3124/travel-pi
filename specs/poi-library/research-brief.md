# Research Brief — A1 Reusable POI Library

**Feature:** `specs/poi-library/design.md` — `saved_places` table + `trip_place_link` M2M shortlist.
**Depth:** Deep (schema change — new tables; new public API contract).
**Bottom line:** This is a near-clone of the existing **trips** stack with one new table + a small
M2M. **Reuse > build.** No new dependency, no external integration, no upstream library needed. The
design already names the right patterns; this brief pins the exact reuse points with evidence.

## 1. Stack (from manifests) — `Local`

Python 3.10+ FastAPI, Pydantic v2, raw `sqlite3` (no ORM), pytest. `requirements.txt`. Layering
`routers → services → crud`; domain exceptions → JSON envelope. (Confirmed: CLAUDE.md + repo.)

## 2. Reuse map (the lightest path) — all `Local`

| Need | Reuse this | Evidence |
|---|---|---|
| Repo + service + DI factory shape | **trips** stack: module singleton `_trip_service = TripService(get_settings().database_path)` + `get_trip_service()` factory + `TripsDep = Annotated[TripService, Depends(get_trip_service)]` | `services/trip_service.py:354,357`; `routers/trips.py:27` |
| Soft-delete | `delete_trip(trip_id, *, when)` → `UPDATE … SET deleted_at=? WHERE id=? AND deleted_at IS NULL`; reads filter `deleted_at IS NULL` | `crud/trip.py` (get_trip/list_trips/delete_trip) |
| Pagination | `PaginationDep` + `PagedResponse[T]` (`total/limit/offset/results`, `.page_of(items)`) → `SavedPlaceListResponse(PagedResponse[SavedPlace])` | `schemas/pagination.py:12,47,52` |
| Friendly short code | `prefixed_code(prefix, resource_id)` → `prefixed_code("SPL", id)` (mirror catalog `PLC-`) | `core/codes.py:34`; `schemas/place.py:69` |
| Distance / dedup | `haversine_km(lat1, lon1, lat2, lon2)` — **takes floats, no None guard** → guard NULL coords before calling | `core/geo.py:12` |
| Catalog resolution | `place_service.get_place(place_id)` (UUID or `PLC-`) for `source="catalog"` | `services/place_service.py:91` |
| JSON-in-TEXT column (`links`) | booking stores `details` via `json.dumps` / `json.loads` — mirror for `links: list[str]` | `crud/booking.py` (`add` / `_row_to_booking`) |
| Startup init | `lifespan` calls `get_booking_service().init_db()` + `get_trip_service().init_db()` → add `get_saved_place_service().init_db()` | `core/lifespan.py:41-42` |
| Test wiring | conftest overrides `app.dependency_overrides[get_trip_service] = lambda: trip_svc` on a temp-DB instance after `init_db()` → add the same for `get_saved_place_service` | `tests/conftest.py:30,34` |
| Error contract | `NotFoundError`→404, `ConflictError`→409, `responses=error_responses(...)`, `hint=` | repo-wide pattern |
| Route ordering | declare `/places/saved…` **before** `GET /places/{place_id}` (capture route) — same as existing `/nearby`,`/route` | `routers/places.py` |

## 3. Notable findings / gotchas — `Local`

- **A0 migration helpers** (`crud/_migrations.py:14,28` `ensure_column` / `ensure_unique_partial_index`)
  are for **column adds on pre-existing tables**. A1 adds **new tables** via `CREATE TABLE IF NOT
  EXISTS`, so `ensure_column` is **not** needed. The `trip_place_link` uniqueness is a **composite**
  `(trip_id, place_id, source)` index — use a plain `CREATE UNIQUE INDEX IF NOT EXISTS` (NOT
  `ensure_unique_partial_index`, which is single-column partial-on-NULL).
- **No migration gate trip:** `risk-corroboration.sh` flags `ALTER TABLE`/`DROP`/`DELETE FROM`, not
  `CREATE TABLE`. A1's additive new tables won't trip `data-loss/migration`. (Still high-risk lane by
  flag count.)
- **DI pattern choice:** mirror **trips** (factory `get_trip_service`), NOT booking's pattern — both
  expose a factory, but trips is the cleaner template and is what conftest already overrides.
- **`get_trip_detail`** (`services/trip_service.py`) is where the additive `places` field is composed —
  it already aggregates day-plan/budget/gaps, so add the resolved shortlist there.
- **Idempotency:** the design uses **dedup-by-distance (409)** for create rather than an
  `Idempotency-Key`. The booking/trip `Idempotency-Key` replay pattern exists (`crud/booking.py`
  `get_by_idempotency_key` + UNIQUE partial index) if a future iteration wants it — not in A1 scope.

## 4. Upstream / Docs

Skipped as low-value: the feature reuses well-established in-repo FastAPI+sqlite patterns; no new
library or external integration. (`Inference` — justified: design cites only internal patterns; a
GitHub/library search would not change the lightest path, which is "clone the trips stack".)

## 5. Recommendation

**Build by mirroring the trips stack**, one new table + a small M2M, resolver in `place_service`:
- New: `schemas/saved_place.py`, `crud/saved_place.py`, `services/saved_place_service.py`.
- Extend: `crud/trip.py` (+`trip_place_link`), `trip_service.py` (shortlist + `get_trip_detail.places`),
  `place_service.py` (`resolve`), `routers/places.py` (saved routes), `routers/trips.py` (shortlist
  routes), `core/lifespan.py` (init), `tests/conftest.py` (override).
- Nothing to adapt from upstream; nothing new to add to the manifest.

**Risk:** high-risk lane (multi-domain + new contracts); additive only; rollback = `git revert` +
optional drop of the two new tables. No data loss in existing tables.
