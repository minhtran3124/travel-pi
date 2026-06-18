# A1 — Reusable POI Library (design)

> Status: approved (2026-06-18). Resolves roadmap item A1 (`specs/agent-platform-roadmap/CHECKLIST.md`).
> Decisions: **Option A** (static catalog + `saved_places` overlay + `trip_place_link` M2M),
> scope **Core + personal toggles**, favorite/visited as **idempotent SET** (not flip),
> TripDetail gains an additive `places` field.

## 1. Motivation

Today `data/places.py` is a read-only seed of 231 POIs; there is no way for a user/agent to **save
a new POI** or build a **reusable place library** that links into multiple trips. Idea adapted from
`itskovacs/trip`: places as first-class, reusable entities. This unblocks `/agent/plan` (B-phase)
and richer itinerary planning.

## 2. Decisions (forks resolved)

- **Catalog vs unify → Option A.** Keep `data/places.py` as the read-only catalog (deterministic
  `PLC-`/UUID ids, existing `/places` untouched — preserves CLAUDE.md "deterministic generation,
  never stored"). Add a **mutable** `saved_places` table (third mutable store, alongside
  bookings/trips). A trip references catalog **or** saved places via a link that carries a
  `source` discriminator.
- **`trip_place_link` shortlist** is a NEW table, distinct from `trip_items` (the scheduled
  itinerary). It is a trip's place **shortlist** (saved-but-not-yet-scheduled). `trip_items` is
  **unchanged** (no schema change, no behavior change) — limits blast radius.
- **favorite/visited = idempotent SET** (`{value: bool}`), not a flip — consistent with the
  project's idempotency theme (Tier 4); a flip is non-idempotent and unsafe under agent retries.
- **TripDetail gains an additive `places` field** (the resolved shortlist) — additive, non-breaking.

## 3. Non-goals

- No change to `trip_items` (place_id stays a free-text catalog ref).
- No change to existing `/places` catalog endpoints.
- No categories-with-color/icon (that is A2), no auth/ownership (single-tenant mock — saved places
  are global).
- No import-from-URL / batch (later B-phase items).

## 4. Data model (2 new tables; no ALTER on existing tables)

```sql
CREATE TABLE IF NOT EXISTS saved_places (
  id           TEXT PRIMARY KEY,   -- UUID; friendly short code SPL-XXXXXX (derived)
  name         TEXT NOT NULL,
  city         TEXT,
  country      TEXT,
  category     TEXT,               -- same vocab as PlaceCategory (validated, free-ish)
  address      TEXT,
  latitude     REAL,
  longitude    REAL,
  price_level  INTEGER,            -- 1..4, nullable
  notes        TEXT,
  favorite     INTEGER NOT NULL DEFAULT 0,   -- bool
  visited      INTEGER NOT NULL DEFAULT 0,   -- bool
  links        TEXT,               -- JSON-encoded list[str]
  duration     INTEGER,            -- minutes, nullable
  created_at   TEXT NOT NULL,
  deleted_at   TEXT                -- soft-delete (house style: filtered from reads)
);

CREATE TABLE IF NOT EXISTS trip_place_link (
  id        TEXT PRIMARY KEY,      -- UUID
  trip_id   TEXT NOT NULL,
  place_id  TEXT NOT NULL,         -- catalog place id OR saved_places.id
  source    TEXT NOT NULL,         -- 'catalog' | 'saved'
  added_at  TEXT NOT NULL
);
-- one shortlist entry per (trip, place, source)
CREATE UNIQUE INDEX IF NOT EXISTS ix_trip_place_link_unique
  ON trip_place_link (trip_id, place_id, source);
```

> Both are NEW tables (`CREATE TABLE IF NOT EXISTS`) — no `ALTER TABLE` on existing tables, so the
> `data-loss/migration` risk gate is not tripped. New columns within these new tables are declared
> in the CREATE, so the A0 `ensure_column` helper is not needed here (it's for column adds to
> pre-existing tables).

**Field storage notes:**
- `links` — Pydantic field `list[str] | None`; the CRUD layer writes it with `json.dumps(...)` and
  reads it with `json.loads(...)` (NULL/empty → `None`/`[]`). Mirrors how `crud/booking.py` stores
  `details` as JSON text.
- `favorite` / `visited` — stored as `0/1` INTEGER, exposed as `bool` in the schema.
- `id` — UUID; friendly `SPL-XXXXXX` short code is a computed field via
  `core/codes.prefixed_code("SPL", id)` (mirrors the catalog's `PLC-`).

## 5. Resolution (catalog ⊕ saved → unified)

A single resolver in `place_service`:

```
resolve(place_id: str, source: Literal["catalog","saved"]) -> ResolvedPlace | None
  source == "catalog" -> place_service.get_place(place_id)         # seed
  source == "saved"   -> saved_place_service.get(place_id)          # DB (excludes soft-deleted)
```

Shortlist responses use a concrete model:

```python
class ShortlistEntry(AppBaseModel):
    link_id: str                          # trip_place_link.id — the handle for DELETE
    source: Literal["catalog", "saved"]
    place: Place | SavedPlace             # resolved body; `source` tells which
```

`place` is a plain union (not a Pydantic internal discriminated union — the two models have
different field sets; the sibling `source` field is the discriminator the caller reads). `link_id`
is included so a client knows exactly what to `DELETE /trips/{id}/places/{link_id}`.

## 6. API surface

**Saved places** (extend the `places` router or a new `saved_places` router; prefer keeping under
`/places/saved` for discoverability):

| Method/Path | Behavior |
|---|---|
| `POST /places/saved` | Create a saved POI. **Dedup:** a non-deleted saved place with the same case-insensitive `name` is a duplicate when — **both** records have coords and are within ~50 m (`haversine_km`), **or** coords are missing on either side and `city` matches. → **409** with the existing id in `hint`. (Guard `haversine_km` against `None` — never call it with a NULL coord.) |
| `GET /places/saved` | List saved places; filters: `city`, `category`, `favorite`, `visited`. Response `SavedPlaceListResponse(PagedResponse[SavedPlace])` using the existing `PaginationDep`/`PagedResponse` pattern. |
| `GET /places/saved/{id}` | Get one (UUID or `SPL-` code); 404 if missing/soft-deleted. |
| `DELETE /places/saved/{id}` | Soft-delete (stamp `deleted_at`), 204. A repeat call returns **404** (the row is already tombstoned/filtered) — same as the trips soft-delete; safe to retry, the status simply changes. |
| `POST /places/saved/{id}/favorite` | Body `{value: bool}` → SET `favorite` (idempotent), return the place. |
| `POST /places/saved/{id}/visited` | Body `{value: bool}` → SET `visited` (idempotent), return the place. |

**Trip shortlist** (trips router):

| Method/Path | Behavior |
|---|---|
| `POST /trips/{id}/places` | Body `{place_id, source?}` (`source` default `"catalog"`). 404 if the place doesn't exist in that source; **409** if already shortlisted (UNIQUE). Returns the created link (resolved). |
| `GET /trips/{id}/places` | List the trip's shortlist, each entry resolved with its `source`. |
| `DELETE /trips/{id}/places/{link_id}` | Remove a shortlist entry; 404 if not on this trip. |

`GET /trips/{id}` (TripDetail) — **add `places: list[ShortlistEntry]`** (additive).

## 7. Layers (clear units, follow existing patterns)

- `app/schemas/saved_place.py` (new) — `SavedPlace`, `SavedPlaceCreate`, `SavedPlaceFlag` (`{value: bool}`), `ShortlistEntry`, request/response envelopes. Keeps `schemas/place.py` from bloating.
- `app/crud/saved_place.py` (new) — `SavedPlaceRepository` (raw SQLite, fresh-conn-per-call, idempotent `init_db`), CRUD + soft-delete + dedup query. Mirrors `crud/trip.py`.
- `app/services/saved_place_service.py` (new) — business rules (id gen, 404/409, dedup via `core/geo.haversine_km`). Expose a `get_saved_place_service()` factory + a `SavedPlaceDep = Annotated[SavedPlaceService, Depends(get_saved_place_service)]` (mirror the **trips** factory pattern, not booking's module singleton) so tests can `app.dependency_overrides[get_saved_place_service]` onto a temp-DB instance — exactly as `tests/conftest.py` overrides `get_trip_service`. `lifespan.py` calls `.init_db()` on this service at startup.
- `app/crud/trip.py` — add `trip_place_link` table to `init_db`; link CRUD (`add_trip_place`, `list_trip_places`, `delete_trip_place`).
- `app/services/trip_service.py` — shortlist orchestration; resolve each entry via `place_service`/`saved_place_service`; extend `get_trip_detail` to include `places`.
- `app/services/place_service.py` — add `resolve(place_id, source)`.
- `app/routers/places.py` — saved-place routes (declared before `/{place_id}` capture route).
- `app/routers/trips.py` — shortlist routes.
- `app/core/lifespan.py` — init the saved-place repo (+ link table via trip repo) on startup.
- `app/core/codes.py` — `SPL-` short code for saved places (mirror `PLC-`).

## 8. Error handling

Domain exceptions only (`NotFoundError`→404, `ConflictError`→409); never `HTTPException` in
services. Dedup and duplicate-shortlist → `ConflictError` with actionable `hint`. Routes declare
codes via `responses=error_responses(...)`.

## 9. Testing

- **saved_place**: create happy-path; dedup-by-distance → 409 (same name <50 m) and allowed (>50 m or different name); get by id + `SPL-` code; list filters (city/category/favorite/visited); favorite/visited SET idempotent (same value twice → same state); soft-delete → 404 + absent from list, idempotent repeat.
- **shortlist**: add catalog place; add saved place; list resolves both with `source`; duplicate → 409; unknown place in source → 404; wrong-source → 404; remove → gone; remove non-existent → 404.
- **TripDetail**: includes `places` (empty by default, populated after add).
- **lifespan/init**: tables created on startup; `init_db` idempotent (re-run no-op).
- New tables ⇒ no legacy-DB ALTER test required (per the A0 convention, that applies to column adds on existing tables).

## 10. Risks

- **Blast radius:** multi-domain (places + trips) + new public endpoints → high-risk lane, full proof
  (per-task + correctness + intent review).
- **Resolver source ambiguity:** mitigated by an explicit `source` discriminator on the link (no
  guessing across id namespaces).
- **TripDetail contract:** the `places` field is additive; existing consumers unaffected.

## 11. Rollback

New tables are additive; `git revert <sha>` removes the code. Orphan tables (`saved_places`,
`trip_place_link`) are harmless if left, or dropped manually. No data loss in existing tables.
