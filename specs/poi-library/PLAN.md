---
slug: poi-library
status: shipped
owner: Minh Tran
created: 2026-06-18
---

# A1 — Reusable POI Library Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Add a mutable `saved_places` store + a `trip_place_link` M2M shortlist, keeping the
read-only `data/places.py` catalog, so places become reusable, first-class entities.

**Architecture:** Mirror the existing **trips** stack (repo + service + factory DI). Two waves:
Wave 1 ships the saved-places store on its own; Wave 2 adds the resolver + trip shortlist (depends
on Wave 1). New tables only (`CREATE TABLE`) — no `ALTER` on existing tables, `trip_items`
unchanged.

**Tech Stack:** FastAPI, Pydantic v2, raw `sqlite3`, pytest. Reuse: `PaginationDep`/`PagedResponse`,
`core/codes.prefixed_code`, `core/geo.haversine_km`, soft-delete pattern, factory-DI + conftest
overrides. (See `research-brief.md` for the exact reuse map.)

---

## 1. Motivation / 2. Non-goals / 3. Success Criteria

See `design.md` §1–3. In short: saved POIs + trip shortlist; favorite/visited as idempotent SET;
dedup-by-distance (409); TripDetail gains additive `places`. Non-goals: no change to `trip_items`,
`/places` catalog, or categories-with-color (A2); no auth.

## File map

| File | Wave | Responsibility |
|---|---|---|
| `app/schemas/saved_place.py` (new) | 1 | `SavedPlace`, `SavedPlaceCreate`, `SavedPlaceFlag`, `SavedPlaceListResponse`, `ShortlistEntry` |
| `app/crud/saved_place.py` (new) | 1 | `SavedPlaceRepository` — SQLite CRUD + soft-delete + dedup query |
| `app/services/saved_place_service.py` (new) | 1 | rules, dedup-by-distance, factory `get_saved_place_service` + `SavedPlaceDep` |
| `app/routers/places.py` (mod) | 1 | `/places/saved…` routes (before `/{place_id}`) |
| `app/core/lifespan.py` (mod) | 1 | init the saved-place repo on startup |
| `tests/conftest.py` (mod) | 1 | override `get_saved_place_service` onto temp DB |
| `app/services/place_service.py` (mod) | 2 | `resolve(place_id, source)` |
| `app/crud/trip.py` (mod) | 2 | `trip_place_link` table + add/list/delete |
| `app/services/trip_service.py` (mod) | 2 | shortlist methods + `get_trip_detail.places` |
| `app/schemas/trip.py` (mod) | 2 | `TripDetail.places: list[ShortlistEntry]` |
| `app/routers/trips.py` (mod) | 2 | `/trips/{id}/places…` routes |
| `tests/test_saved_places.py` (new) | 1 | saved store tests |
| `tests/test_trip_shortlist.py` (new) | 2 | shortlist tests |

---

## Chunk 1 — Wave 1: Saved-places store

### Task 1.1 — `schemas/saved_place.py`

**Files:** Create `app/schemas/saved_place.py`.

- [ ] **Step 1: Implement** (verify against `schemas/place.py` for `Field`/`computed_field`/`prefixed_code` usage):

```python
"""Saved (user/agent-created) place schemas — the mutable POI overlay."""

from pydantic import Field, computed_field

from app.core.codes import prefixed_code
from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse
from app.schemas.place import Place

SAVED_PLACE_CODE_PREFIX = "SPL"


class SavedPlaceCreate(AppBaseModel):
    name: str = Field(min_length=1, description="POI name.", examples=["Secret rooftop bar"])
    city: str | None = Field(default=None, examples=["Hanoi"])
    country: str | None = None
    category: str | None = Field(default=None, examples=["nightlife"])
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    price_level: int | None = Field(default=None, ge=1, le=4, examples=[2])
    notes: str | None = None
    links: list[str] | None = Field(default=None, examples=[["https://maps.app.goo.gl/x"]])
    duration: int | None = Field(default=None, ge=0, description="Typical visit minutes.")
    favorite: bool = False
    visited: bool = False


class SavedPlace(SavedPlaceCreate):
    id: str = Field(description="Saved-place UUID.")
    created_at: str = Field(description="ISO-8601 creation timestamp.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def short_code(self) -> str:
        """Friendly ``SPL-XXXXXX`` reference (mirrors catalog ``PLC-``)."""
        return prefixed_code(SAVED_PLACE_CODE_PREFIX, self.id)


class SavedPlaceFlag(AppBaseModel):
    """Body for the favorite/visited SET endpoints (idempotent)."""

    value: bool = Field(description="Target flag value.", examples=[True])


class SavedPlaceListResponse(PagedResponse[SavedPlace]):
    """Response body for ``GET /places/saved``."""


class ShortlistEntry(AppBaseModel):
    """One place on a trip's shortlist (catalog or saved), resolved."""

    link_id: str = Field(description="trip_place_link id — the handle for DELETE.")
    source: str = Field(description="'catalog' or 'saved'.", examples=["catalog"])
    place: Place | SavedPlace = Field(description="Resolved place; `source` says which model.")
```

- [ ] **Step 2: Verify import + construct:**

Run: `.venv/bin/python -c "from app.schemas.saved_place import SavedPlace, SavedPlaceCreate, SavedPlaceFlag, SavedPlaceListResponse, ShortlistEntry; print(SavedPlace(id='x', created_at='t', name='n').short_code)"`
Expected: prints an `SPL-…` code, exit 0.

**Done:** models import; `short_code` derives.

### Task 1.2 — `crud/saved_place.py` + crud tests (TDD)

**Files:** Create `app/crud/saved_place.py`; Test `tests/test_saved_places.py`.

Mirror `crud/trip.py` structure: `_SCHEMA` (the `saved_places` CREATE TABLE from design.md §4),
`_COLUMNS`, `_row_to_saved_place` (decode `links` via `json.loads`, coerce `favorite/visited` to
bool), `_values` (encode `links` via `json.dumps`), a `@contextmanager _connect`, and:

```python
class SavedPlaceRepository:
    def __init__(self, db_path: str) -> None: ...
    def init_db(self) -> None:
        # CREATE TABLE IF NOT EXISTS saved_places (...)  # design.md §4 DDL
        ...
    def add(self, sp: SavedPlace) -> SavedPlace: ...
    def get(self, id_: str) -> SavedPlace | None:
        # by raw UUID OR SPL- short code (case-insensitive), WHERE deleted_at IS NULL
        ...
    def list(self, *, city=None, category=None, favorite=None, visited=None) -> list[SavedPlace]:
        # WHERE deleted_at IS NULL + optional filters, newest first
        ...
    def soft_delete(self, id_: str, *, when: str) -> bool:
        # UPDATE ... SET deleted_at=? WHERE id=? AND deleted_at IS NULL
        ...
    def set_flag(self, id_: str, field: str, value: bool) -> bool:
        # field in {"favorite","visited"} only (guard); UPDATE ... WHERE deleted_at IS NULL
        ...
    def find_duplicate(self, *, name: str, city: str|None, lat: float|None, lng: float|None,
                       radius_km: float) -> SavedPlace | None:
        # non-deleted, same name (case-insensitive). If both have coords → within radius_km
        # (haversine, computed in Python over candidates). Else → same city. None coords never
        # reach haversine.
        ...
```

> `find_duplicate`: fetch non-deleted rows with `LOWER(name)=LOWER(?)`, then in Python pick the
> first where `(lat is not None and lng is not None and cand.lat is not None and cand.lng is not None
> and haversine_km(lat,lng,cand.lat,cand.lng) <= radius_km)` OR `(coords missing on either side and
> cand.city == city)`. Guards `haversine_km` from `None`.

- [ ] **Step 1: Write failing crud tests** — `tests/test_saved_places.py` (crud section), using a `repo` fixture like `tests/test_trips.py`'s (`SavedPlaceRepository(str(tmp_path/'sp.db'))`, `init_db()`):

```python
def test_add_and_get_by_id_and_code(repo):
    sp = repo.add(_make_sp(id="a1", name="Bar"))
    assert repo.get("a1").name == "Bar"
    assert repo.get(sp.short_code).id == "a1"  # SPL- code lookup


def test_soft_delete_filters(repo):
    repo.add(_make_sp(id="a1", name="Bar"))
    assert repo.soft_delete("a1", when="2026-06-18T00:00:00+00:00") is True
    assert repo.get("a1") is None
    assert repo.soft_delete("a1", when="...") is False  # already gone


def test_set_flag(repo):
    repo.add(_make_sp(id="a1", name="Bar"))
    repo.set_flag("a1", "favorite", True)
    assert repo.get("a1").favorite is True


def test_find_duplicate_by_distance(repo):
    repo.add(_make_sp(id="a1", name="Bar", lat=21.0, lng=105.8))
    near = repo.find_duplicate(name="bar", city=None, lat=21.0001, lng=105.8001, radius_km=0.05)
    assert near is not None and near.id == "a1"
    far = repo.find_duplicate(name="bar", city=None, lat=22.0, lng=106.0, radius_km=0.05)
    assert far is None


def test_find_duplicate_no_coords_uses_city(repo):
    repo.add(_make_sp(id="a1", name="Bar", city="Hanoi"))
    assert repo.find_duplicate(name="bar", city="Hanoi", lat=None, lng=None, radius_km=0.05)
    assert repo.find_duplicate(name="bar", city="Hue", lat=None, lng=None, radius_km=0.05) is None
```

(Define `_make_sp(**over)` building a **`SavedPlace`** instance directly — with `id` + `created_at`
populated (NOT `SavedPlaceCreate`), since `repo.add()` takes a full `SavedPlace` — like `_make_trip`.)

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_saved_places.py -q` → FAIL (module missing).
- [ ] **Step 3:** Implement `crud/saved_place.py` per the structure above.
- [ ] **Step 4:** Run the crud tests → PASS. `ruff check app/crud/saved_place.py tests/test_saved_places.py` clean.

**Done:** repo CRUD + dedup query green.

### Task 1.3 — `services/saved_place_service.py` + wiring

**Files:** Create `app/services/saved_place_service.py`; Modify `app/core/lifespan.py`, `tests/conftest.py`.

- [ ] **Step 1: Implement service** (mirror `services/trip_service.py` factory at lines 354–357):

```python
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.crud.saved_place import SavedPlaceRepository
from app.exceptions import ConflictError, NotFoundError
from app.schemas.saved_place import SavedPlace, SavedPlaceCreate

_DEDUP_RADIUS_KM = 0.05  # ~50 m


class SavedPlaceService:
    def __init__(self, db_path: str) -> None:
        self._repo = SavedPlaceRepository(db_path)

    def init_db(self) -> None:
        self._repo.init_db()

    def create(self, request: SavedPlaceCreate) -> SavedPlace:
        dup = self._repo.find_duplicate(
            name=request.name, city=request.city,
            lat=request.latitude, lng=request.longitude, radius_km=_DEDUP_RADIUS_KM,
        )
        if dup is not None:
            raise ConflictError(
                f"A saved place named {request.name!r} already exists nearby.",
                hint=f"Reuse {dup.short_code} (id {dup.id}) instead of creating a duplicate.",
            )
        sp = SavedPlace(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            **request.model_dump(),
        )
        return self._repo.add(sp)

    def get(self, id_: str) -> SavedPlace:
        sp = self._repo.get(id_)
        if sp is None:
            raise NotFoundError(f"Saved place {id_!r} not found",
                                hint="Use GET /places/saved to list saved places.")
        return sp

    def list(self, **filters) -> list[SavedPlace]:
        return self._repo.list(**filters)

    def delete(self, id_: str) -> None:
        self.get(id_)  # 404 if missing/already-deleted
        self._repo.soft_delete(id_, when=datetime.now(timezone.utc).isoformat())

    def set_flag(self, id_: str, field: str, value: bool) -> SavedPlace:
        self.get(id_)
        self._repo.set_flag(id_, field, value)
        return self.get(id_)


_saved_place_service = SavedPlaceService(get_settings().database_path)


def get_saved_place_service() -> SavedPlaceService:
    return _saved_place_service
```

- [ ] **Step 2: Wire startup** — in `app/core/lifespan.py`, import `get_saved_place_service` and add `get_saved_place_service().init_db()` next to the trip/booking inits (lifespan.py:41–42).

- [ ] **Step 3: Wire tests** — in `tests/conftest.py`, mirror the trip override: build `SavedPlaceService(tmp_db)`, `init_db()`, and `app.dependency_overrides[get_saved_place_service] = lambda: sp_svc` (conftest.py:30,34).

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/ -q` → still green (no routes yet; wiring must not break startup).

**Done:** service + startup + test wiring in place.

### Task 1.4 — `/places/saved` routes + HTTP tests

**Files:** Modify `app/routers/places.py`; Test `tests/test_saved_places.py` (HTTP section).

- [ ] **Step 1: Write failing HTTP tests** (append to `tests/test_saved_places.py`):

```python
def test_create_get_list_saved(client):
    r = client.post("/places/saved", json={"name": "Rooftop", "city": "Hanoi", "category": "nightlife"})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert client.get(f"/places/saved/{sid}").status_code == 200
    assert any(p["id"] == sid for p in client.get("/places/saved").json()["results"])


def test_dedup_conflict(client):
    body = {"name": "Twin", "latitude": 21.0, "longitude": 105.8}
    assert client.post("/places/saved", json=body).status_code == 201
    assert client.post("/places/saved", json={**body, "latitude": 21.0001, "longitude": 105.8001}).status_code == 409


def test_favorite_set_idempotent(client):
    sid = client.post("/places/saved", json={"name": "X"}).json()["id"]
    for _ in range(2):
        r = client.post(f"/places/saved/{sid}/favorite", json={"value": True})
        assert r.status_code == 200 and r.json()["favorite"] is True


def test_soft_delete_saved(client):
    sid = client.post("/places/saved", json={"name": "Y"}).json()["id"]
    assert client.delete(f"/places/saved/{sid}").status_code == 204
    assert client.get(f"/places/saved/{sid}").status_code == 404
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_saved_places.py -k "client or saved" -q` → FAIL (404, routes missing).

- [ ] **Step 3: Add routes** in `app/routers/places.py` — **declare ALL of them before the existing `GET /{place_id}`** capture route. Import `SavedPlaceDep` (define it in the service module as `SavedPlaceDep = Annotated[SavedPlaceService, Depends(get_saved_place_service)]`) and the schemas. Routes:
  - `POST /places/saved` (201, `response_model=SavedPlace`, `responses=error_responses(409, 422)`) → `service.create(body)`.
  - `GET /places/saved` (`response_model=SavedPlaceListResponse`) with `PaginationDep` + query filters `city/category/favorite/visited`. Explicit pattern (mirror `routers/places.py:40-43,119-132`): `page, total = pagination.page_of(service.list(city=..., category=..., favorite=..., visited=...))`, then `return SavedPlaceListResponse(total=total, limit=pagination.limit, offset=pagination.offset, results=page)`.
  - `GET /places/saved/{saved_id}` (`response_model=SavedPlace`, `responses=error_responses(404)`).
  - `DELETE /places/saved/{saved_id}` (`status_code=204`, `responses=error_responses(404)`).
  - `POST /places/saved/{saved_id}/favorite` and `/visited` (`response_model=SavedPlace`, body `SavedPlaceFlag`) → `service.set_flag(saved_id, "favorite"/"visited", body.value)`.

- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_saved_places.py -q && .venv/bin/python -m pytest tests/ -q` → all pass. `ruff check` clean.

**Done:** Wave 1 ships — saved POIs creatable, listable, flaggable, soft-deletable; dedup 409.

---

## Chunk 2 — Wave 2: Resolver + trip shortlist

### Task 2.1 — `place_service.resolve`

**Files:** Modify `app/services/place_service.py`.

- [ ] Add a resolver returning the catalog `Place` or `SavedPlace` (or `None`):

```python
def resolve(place_id: str, source: str):
    """Resolve a shortlisted place. source: 'catalog' | 'saved'."""
    if source == "saved":
        from app.services.saved_place_service import get_saved_place_service
        return get_saved_place_service()._repo.get(place_id)  # None if missing/deleted
    return get_place(place_id)  # catalog seed (None if unknown)
```

> Import inside the function to avoid a circular import (place_service ↔ saved_place_service). Verify no cycle at startup.

- [ ] Verify: `.venv/bin/python -c "from app.services import place_service"` exit 0.

### Task 2.2 — `trip_place_link` table + CRUD

**Files:** Modify `app/crud/trip.py`.

- [ ] In `init_db`, after the existing tables, add the `trip_place_link` CREATE TABLE + the composite UNIQUE index (design.md §4) — use a **plain** `CREATE UNIQUE INDEX IF NOT EXISTS ix_trip_place_link_unique ON trip_place_link (trip_id, place_id, source)` (NOT the A0 `ensure_unique_partial_index`, which is single-column partial).
- [ ] Add methods (raw SQL, mirror existing trip methods):

```python
def add_trip_place(self, link_id, trip_id, place_id, source, added_at) -> None:
    # INSERT; on sqlite3.IntegrityError (UNIQUE) re-raise — service maps to 409
def list_trip_places(self, trip_id) -> list[sqlite3.Row]:
    # SELECT * FROM trip_place_link WHERE trip_id=? ORDER BY added_at
def get_trip_place(self, link_id) -> sqlite3.Row | None: ...
def delete_trip_place(self, trip_id, link_id) -> bool:
    # DELETE WHERE id=? AND trip_id=?  → rowcount>0
```

- [ ] Verify import: `.venv/bin/python -c "from app.crud.trip import TripRepository"` exit 0.

### Task 2.3 — Trip service shortlist + `TripDetail.places`

**Files:** Modify `app/services/trip_service.py`, `app/schemas/trip.py`.

- [ ] In `schemas/trip.py`, add `places: list[ShortlistEntry] = Field(default_factory=list, ...)` to `TripDetail` (import `ShortlistEntry` from `schemas.saved_place`). Additive.
- [ ] In `trip_service.py`, add:
  - `add_place_to_trip(trip_id, place_id, source="catalog") -> ShortlistEntry`: **first** validate `source in {"catalog","saved"}` → else raise `ConflictError`/`BadRequest` (422-ish; reuse the project's validation error) BEFORE any DB call; then `self.get_trip(trip_id)` (404 if no trip); validate the place resolves via `place_service.resolve(place_id, source)` (404 `NotFoundError` if `None`); generate `link_id`, call `self._repo.add_trip_place(...)`; on `sqlite3.IntegrityError` → `ConflictError` (409, already shortlisted); return a resolved `ShortlistEntry`.
  - `list_trip_places(trip_id) -> list[ShortlistEntry]`: get_trip (404), map each link row → resolve → `ShortlistEntry(link_id, source, place)`. Skip/drop rows whose place no longer resolves (e.g. a saved place was deleted) — or include with a tombstone; **default: drop** and note it.
  - `remove_trip_place(trip_id, link_id) -> None`: get_trip; `self._repo.delete_trip_place(...)`; 404 if rowcount 0.
  - In `get_trip_detail`, set `places=self.list_trip_places(trip_id)`.
- [ ] Validate `source` ∈ {"catalog","saved"} at the service boundary (else `NotFoundError`/422).

### Task 2.4 — Trip shortlist routes + tests

**Files:** Modify `app/routers/trips.py`; Test `tests/test_trip_shortlist.py`.

- [ ] **Step 1: Failing tests** — `tests/test_trip_shortlist.py`:

```python
def _trip(client): return client.post("/trips", json={"title": "T", "travelers": 1}).json()["id"]


def test_add_catalog_place_to_trip(client):
    tid = _trip(client)
    pid = client.get("/places", params={"limit": 1}).json()["results"][0]["id"]
    r = client.post(f"/trips/{tid}/places", json={"place_id": pid, "source": "catalog"})
    assert r.status_code == 201 and r.json()["source"] == "catalog"
    lst = client.get(f"/trips/{tid}/places").json()
    assert len(lst) == 1 and lst[0]["place"]["id"] == pid
    # additive on TripDetail
    assert client.get(f"/trips/{tid}").json()["places"][0]["place"]["id"] == pid


def test_add_saved_place_and_dedupe_409(client):
    tid = _trip(client)
    sid = client.post("/places/saved", json={"name": "S"}).json()["id"]
    body = {"place_id": sid, "source": "saved"}
    first = client.post(f"/trips/{tid}/places", json=body)
    assert first.status_code == 201
    assert client.post(f"/trips/{tid}/places", json=body).status_code == 409  # duplicate


def test_unknown_place_404_and_remove(client):
    tid = _trip(client)
    assert client.post(f"/trips/{tid}/places", json={"place_id": "nope", "source": "catalog"}).status_code == 404
    pid = client.get("/places", params={"limit": 1}).json()["results"][0]["id"]
    link_id = client.post(f"/trips/{tid}/places", json={"place_id": pid}).json()["link_id"]
    assert client.delete(f"/trips/{tid}/places/{link_id}").status_code == 204
    assert client.get(f"/trips/{tid}/places").json() == []
```

- [ ] **Step 2:** Run → FAIL (routes missing).
- [ ] **Step 3: Add routes** in `app/routers/trips.py` (use existing `TripsDep`, `_TRIP_ID`). First declare the request body schema in `app/schemas/trip.py` (so `source` has a real default):
  ```python
  class AddTripPlaceRequest(AppBaseModel):
      place_id: str = Field(description="Catalog place id (UUID/PLC-) or saved_places id.")
      source: str = Field(default="catalog", description="'catalog' or 'saved'.")
  ```
  - `POST /trips/{trip_id}/places` (201, `response_model=ShortlistEntry`, `responses=error_responses(404, 409, 422)`) body `AddTripPlaceRequest` → `trips.add_place_to_trip(trip_id, body.place_id, body.source)`.
  - `GET /trips/{trip_id}/places` (`response_model=list[ShortlistEntry]`, `responses=error_responses(404)`).
  - `DELETE /trips/{trip_id}/places/{link_id}` (204, `responses=error_responses(404)`).
- [ ] **Step 4:** Run `.venv/bin/python -m pytest tests/test_trip_shortlist.py tests/test_trips.py -q && .venv/bin/python -m pytest tests/ -q` → all pass. `ruff check` clean.

**Done:** Wave 2 ships — catalog & saved places shortlist onto trips; TripDetail shows them.

---

## 5. Risks

- **Circular import** place_service ↔ saved_place_service — mitigated by the in-function import in `resolve` (Task 2.1); verified by the import smoke check.
- **Deleted saved place still linked** — `list_trip_places` drops entries that no longer resolve (documented); the link row is harmless residue.
- **Route ordering** — `/places/saved…` MUST precede `GET /places/{place_id}`; Task 1.4 calls this out.
- **TripDetail contract** — `places` is additive (`default_factory=list`); existing consumers unaffected.
- **High-risk lane** — full proof: per-task spec+quality review, final correctness + intent review.

## 6. Rollback

`git revert <shas>`. New tables (`saved_places`, `trip_place_link`) are additive — orphan tables are
harmless or droppable; no existing-table schema/data change.

## 7. Status Log

- 2026-06-18 — Plan drafted (proposed). High-risk lane (multi-domain + new contracts; additive, no migration gate). Inputs: design.md + research-brief.md.

- 2026-06-18 — shipped via `feat/poi-library` (PR pending, base `v2`). Waves 1+2; 594 tests.
