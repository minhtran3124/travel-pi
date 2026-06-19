---
slug: seed-data-orm-models
status: proposed
lane: high-risk
---

# Seed Data → ORM Models Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use subagent-driven-development (or executing-plans) to implement this plan task-by-task.

**Goal:** Persist the 9 read-only `app/data/` seed entities into the database via SQLAlchemy ORM, restructure `app/db/models.py` into a per-entity package (classes named without the `Row` suffix), serve them through per-request DB queries via per-entity repos, and seed the DB idempotently from `app/data` — without breaking the public API contract, the deterministic generation invariants, or the parity test suite.

**Architecture:** New ORM models in `app/db/models/` (one file per entity, `models.` namespace to disambiguate from the identically-named `app/schemas/` Pydantic models). Per-entity repos in `app/crud/` take a `session_factory`, run SQL for exact/range filters, and refine fuzzy (`core/text.py`) + JSON-list predicates in Python over DB-fetched candidate sets; they return the existing Pydantic response models. An idempotent `app/db/seed.py` upserts every entity from `app/data` (kept as the guarded source of truth) via `session.merge()`, wired into lifespan + `make seed` + the pytest session fixture. New Alembic revision `0002_seed_entities`.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), psycopg 3, Alembic, dual-engine SQLite(default/tests)+Postgres(Docker).

**Input artifacts:** `specs/seed-data-orm-models/design.md` (approved), `specs/seed-data-orm-models/research-brief.md` (column inventory + the exact ~15 consumer call sites — **read it; tasks below reference it**).

**Parity gate:** Suite (currently **621**) stays green on SQLite after every chunk and on real Postgres (`make test-docker`) at the end of each chunk that touches read paths. New tests are added; re-baseline with `pytest --collect-only -q | tail -1`. Tests that import `app.data` directly stay green because **`app/data/*` is kept**.

**Five non-negotiable invariants (from the research brief):**
1. **Airline order is load-bearing.** `flight_service.generate_flights` does `rng.choice(AIRLINES)` over a *seeded* RNG → `Airline` needs a `position` column and `airlines_repo` MUST `ORDER BY position`. Golden determinism test required.
2. **`Hotel.country`** is already filled on every `HOTELS` record at *import* time (`hotels.py:~3475` mutates `_hotel["country"] = _COUNTRY_BY_CITY[city]`), so the seeder maps `country` **straight from the record** (no lookup needed). Tests assert it's present + matches the city → just preserve it.
3. **UUIDs stored as `String`, seeded verbatim** (hotel/place ids feed MD5 seeds + `short_code`).
4. **Tip IDs are positional** (`tip_{scope}_{prefix}_{NN}`) → `position` column; seeder inserts in `COUNTRY_TIPS`/`CITY_TIPS` list order. `CountrySummary` is its own table.
5. **`app/data` import-time guards must not be weakened** — they run on import-for-seeding.

---

## File Structure

**New:**
- `app/db/models/` package: `__init__.py`, `booking.py`, `trip.py`, `saved_place.py`, `flight_index.py` (moved+renamed), `country.py`, `airline.py`, `airport.py`, `city.py`, `hotel.py`, `place.py`, `tip.py`, `visa.py`, `fx.py` (new)
- `app/db/seed.py` — idempotent seeder
- `app/crud/`: `country.py`, `airline.py`, `airport.py`, `city.py`, `hotel_ref.py`, `place_ref.py`, `tip.py`, `visa.py`, `fx.py` (new repos; `_ref` suffix avoids clashing with any existing crud)
- `alembic/versions/0002_seed_entities.py`
- `tests/db/test_seed.py`, `tests/db/test_determinism.py`, `tests/crud/test_reference_repos.py`

**Modified:**
- delete `app/db/models.py` (becomes the package); update imports in `app/crud/{booking,trip,saved_place,flight}.py`, `tests/conftest.py`, `tests/test_db_models.py`, `alembic/env.py`
- `app/core/lifespan.py` (seed on startup), `Makefile` (`seed` target)
- consumers (Chunk E): `app/routers/{cities,dashboard}.py`, `app/core/invariants.py`, `app/services/{destination,flight,airport,routing,place,visa,currency,hotel,board,tip}_service.py`
- `app/schemas/*` only if a DRY win appears (no contract change)
- `README.md`, `CLAUDE.md`

**Kept unchanged:** `app/data/*.py` (seed source + guards), all `app/schemas/*` response shapes.

---

## Chunk A: Golden fixture + models package split + rename (no behavior change)

> Pure refactor: move the 6 shipped ORM classes into a package and drop the `Row` suffix. `__tablename__`s and columns are untouched → DB schema, `0001_initial`, and `alembic check` are unaffected. Suite must stay green. **But first** capture golden determinism fixtures on the *clean* tree — this is the only way to prove (in Chunk F) that the airline-order + UUID invariants survived the migration.

### Task A0: Capture golden determinism fixtures on the pre-migration tree

**Files:** Create `tests/db/fixtures/golden_flights.json`, `tests/db/fixtures/golden_hotel_availability.json`.

- [ ] **Step 1:** With the worktree on clean HEAD (no migration code yet), run the real endpoints via a throwaway script/TestClient and dump the JSON for fixed queries: `GET /flights/search?origin=SGN&destination=HAN&departure_date=2026-09-01` and `GET /hotels/{a fixed seeded hotel id}/availability?check_in=2026-09-01&check_out=2026-09-04`. Save the response bodies verbatim to the two fixture files.
- [ ] **Step 2:** Commit the fixtures. Chunk F asserts post-migration output **byte-equals** these on both engines. (Do NOT regenerate them after code changes — they are the pre-migration oracle.)

### Task A1: Create the package and move classes

**Files:** Create `app/db/models/__init__.py` + one file per existing entity; Delete `app/db/models.py`.

- [ ] **Step 1:** Create `app/db/models/booking.py` with the `BookingRow` class body from `app/db/models.py`, **renamed `Booking`**. Repeat into `trip.py` (`Trip`, `TripItem`, `TripPlaceLink`), `saved_place.py` (`SavedPlace`), `flight_index.py` (`FlightIndex`). Each imports `from app.db.base import Base` and the SQLAlchemy symbols it uses.
- [ ] **Step 2:** Write `app/db/models/__init__.py` re-exporting every class:

```python
"""ORM models package. Reference via the namespace: `models.Hotel`, `models.Booking`.
Class names intentionally match app/schemas Pydantic models — disambiguate by import
(`from app.db import models` → models.X) vs (`from app.schemas.x import X`)."""

from app.db.models.booking import Booking
from app.db.models.trip import Trip, TripItem, TripPlaceLink
from app.db.models.saved_place import SavedPlace
from app.db.models.flight_index import FlightIndex
# Chunk B appends: Country, Airline, Airport, City, Hotel, Place, Tip, CountrySummary,
# Visa, FxRate, CountryCurrency, FxMeta

__all__ = [
    "Booking", "Trip", "TripItem", "TripPlaceLink", "SavedPlace", "FlightIndex",
]
```

- [ ] **Step 3:** Delete `app/db/models.py`.

### Task A2: Update all references to the renamed classes

**Files:** `app/crud/{booking,trip,saved_place,flight}.py`, `tests/conftest.py`, `tests/test_db_models.py`, `alembic/env.py`.

- [ ] **Step 1:** In each crud file, change `from app.db.models import BookingRow` → `from app.db import models` and replace `BookingRow`→`models.Booking`, `TripRow`→`models.Trip`, etc. (Use the namespace form — it is the project convention going forward.)
- [ ] **Step 2:** `alembic/env.py`: confirm `from app.db import models  # noqa: F401` still registers everything (it imports the package, whose `__init__` imports all classes). Update `tests/test_db_models.py` references (`BookingRow`→`models.Booking`, table-name assertions unchanged).
- [ ] **Step 3:** `grep -rn "Row\b" app/ tests/` → only matches should be unrelated words. `grep -rn "from app.db.models import .*Row\|[A-Za-z]Row(" app/ tests/` → empty.

### Task A3: Verify the refactor is behavior-neutral

- [ ] **Step 1:** `.venv/bin/python -m pytest tests/ -q` → full count still green (621).
- [ ] **Step 2:** `.venv/bin/alembic upgrade head` against a temp sqlite (`DATABASE_URL=sqlite:////tmp/a.db`) then `.venv/bin/alembic check` → **no drift** (proves the rename didn't touch the schema). `.venv/bin/ruff check app tests`.

---

## Chunk B: New ORM models + Alembic 0002

### Task B1: Country, Airline, Airport, City models

**Files:** Create `app/db/models/{country,airline,airport,city}.py`; append to `__init__.py`.

- [ ] **Step 1:** `country.py`:

```python
from sqlalchemy import Float, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Country(Base):
    __tablename__ = "countries"
    code: Mapped[str] = mapped_column(String, primary_key=True)        # "VN"
    name: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    # Unique index on name so City.country (a name) can FK against it.
    __table_args__ = (Index("ix_countries_name", "name", unique=True),)
```

> **FK-by-name caveat:** `cities.country`→`countries.name` is valid SQLAlchemy 2.0 only because `countries.name` is unique (above). **SQLite does not enforce FKs** unless `PRAGMA foreign_keys=ON` per connection (off by default) — so on the test engine the FK is documentation-only; the **real cross-table guarantee remains the retained `app/data` import guards** (do not treat the FK as a replacement). On Postgres it is enforced. In Task B4, hand-verify the generated `0002` references `countries.name`'s unique index and that `downgrade` drops the FK before the index.

- [ ] **Step 2:** `airline.py` — **note the `position` column (determinism):**

```python
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Airline(Base):
    __tablename__ = "airlines"
    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # AIRLINES seed order
    color: Mapped[str | None] = mapped_column(String, nullable=True)  # AIRLINE_COLORS
```

- [ ] **Step 3:** `airport.py`:

```python
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Airport(Base):
    __tablename__ = "airports"
    iata: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"), nullable=False)
```

- [ ] **Step 4:** `city.py` — `country` is the **name**, FK→`countries.name` (the unique index from B1):

```python
from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class City(Base):
    __tablename__ = "cities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(ForeignKey("countries.name"), nullable=False)  # name
    country_code: Mapped[str | None] = mapped_column(String, nullable=True)  # denormalized
    airport_codes: Mapped[list] = mapped_column(JSON, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (Index("ix_cities_name_country", "name", "country", unique=True),)
```

- [ ] **Step 5:** Append `Country, Airline, Airport, City` to `__init__.py` `__all__` + imports.

### Task B2: Hotel, Place models (the rich ones — enumerate ALL columns)

**Files:** Create `app/db/models/{hotel,place}.py`; append to `__init__.py`.

- [ ] **Step 1:** `hotel.py` (columns from `app/schemas/hotel.py` + `hotels.py`; `country` seed-filled; `short_code` is NOT stored — it's a Pydantic computed property):

```python
from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Hotel(Base):
    __tablename__ = "hotels"
    id: Mapped[str] = mapped_column(String, primary_key=True)   # UUID string, verbatim
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)  # seed-filled from city
    address: Mapped[str] = mapped_column(String, nullable=False)
    star_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_night: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    amenities: Mapped[list] = mapped_column(JSON, nullable=False)
    image_url: Mapped[str] = mapped_column(String, nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    property_type: Mapped[str] = mapped_column(String, nullable=False)
    chain: Mapped[str] = mapped_column(String, nullable=False)
    check_in_time: Mapped[str] = mapped_column(String, nullable=False)
    check_out_time: Mapped[str] = mapped_column(String, nullable=False)
    breakfast_included: Mapped[bool] = mapped_column(Boolean, nullable=False)
    free_cancellation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    languages_spoken: Mapped[list] = mapped_column(JSON, nullable=False)
```

> Verify the exact field set against `app/schemas/hotel.py` (read the whole class) before finalizing — the model must carry every field the `Hotel` schema requires so `Hotel(**row_dict)` validates.

- [ ] **Step 2:** `place.py` (from `app/schemas/place.py` + `places.py`):

```python
from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Place(Base):
    __tablename__ = "places"
    id: Mapped[str] = mapped_column(String, primary_key=True)   # UUID string, verbatim
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str] = mapped_column(String, nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    price_level: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_hours: Mapped[str | None] = mapped_column(String, nullable=True)
    image_url: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False)
    is_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
```

### Task B3: Tip, CountrySummary, Visa, Fx models

**Files:** Create `app/db/models/{tip,visa,fx}.py`; append to `__init__.py`.

- [ ] **Step 1:** `tip.py`:

```python
from sqlalchemy import Boolean, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Tip(Base):
    __tablename__ = "tips"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # tip_{scope}_{prefix}_{NN}
    scope: Mapped[str] = mapped_column(String, nullable=False)  # "country" | "city"
    key: Mapped[str] = mapped_column(String, nullable=False)    # country or city name
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_essential: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    __table_args__ = (Index("ix_tips_scope_key_position", "scope", "key", "position", unique=True),)

class CountrySummary(Base):
    __tablename__ = "country_summaries"
    country: Mapped[str] = mapped_column(String, primary_key=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
```

- [ ] **Step 2:** `visa.py`:

```python
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Visa(Base):
    __tablename__ = "visa"
    country: Mapped[str] = mapped_column(String, primary_key=True)
    visa_free_days: Mapped[int] = mapped_column(Integer, nullable=False)
    visa_on_arrival: Mapped[bool] = mapped_column(Boolean, nullable=False)
    e_visa: Mapped[bool] = mapped_column(Boolean, nullable=False)
    passport_validity_months: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
```

- [ ] **Step 3:** `fx.py`:

```python
from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class FxRate(Base):
    __tablename__ = "fx_rates"
    code: Mapped[str] = mapped_column(String, primary_key=True)   # ISO 4217
    rate: Mapped[float] = mapped_column(Float, nullable=False)    # units per 1 USD
    name: Mapped[str] = mapped_column(String, nullable=False)     # from CURRENCY_NAMES

class CountryCurrency(Base):
    __tablename__ = "country_currency"
    country: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)

class FxMeta(Base):
    __tablename__ = "fx_meta"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)  # singleton row
    last_updated: Mapped[str] = mapped_column(String, nullable=False)
```

- [ ] **Step 4:** Append all new classes to `__init__.py`. **Update the existing strict assertion in `tests/test_db_models.py`** (it asserts `set(Base.metadata.tables) == {the 6 original tables}` — this BREAKS once new tables register): extend that set to include the new table names (`countries, airlines, airports, cities, hotels, places, tips, country_summaries, visa, fx_rates, country_currency, fx_meta`), or change `==` to `>=`/`<=` as appropriate. Without this, the parity gate fails at Chunk B.

### Task B4: Alembic 0002_seed_entities

**Files:** Create `alembic/versions/0002_seed_entities.py`.

- [ ] **Step 1:** Autogenerate against scratch Postgres (Docker is available):
  `docker run --rm -d --name pg-seed -e POSTGRES_PASSWORD=x -p 55434:5432 postgres:17-alpine`, wait for `pg_isready`, then
  `DATABASE_URL=postgresql+psycopg://postgres:x@localhost:55434/postgres .venv/bin/alembic upgrade head` (applies 0001), then
  `… alembic revision --autogenerate -m "seed entities"`. Rename file to `0002_seed_entities.py`, keep `down_revision` = the 0001 revision id.
- [ ] **Step 2:** Review: all new tables + the unique indexes (`ix_countries_name`, `ix_cities_name_country`, `ix_tips_scope_key_position`) + the FKs (`airports.country_code`→countries.code, `cities.country`→countries.name). Hand-fix any dropped index/FK.
- [ ] **Step 3:** Round-trip on scratch PG: `upgrade head` / `downgrade -1` (back to 0001) / `upgrade head`; then `alembic check` → no drift. Tear down `docker rm -f pg-seed`.
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/ -q` (SQLite path uses `create_all`, picks up new tables) → green.

---

## Chunk C: Seeder + lifespan / make / test wiring

### Task C1: `app/db/seed.py`

**Files:** Create `app/db/seed.py`; Test `tests/db/test_seed.py`.

- [ ] **Step 1: Write the failing idempotency test** (`tests/db/test_seed.py`):

```python
from sqlalchemy import func, select
from app.db.base import Base
from app.db import models
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all

def _fresh(tmp_path):
    url = f"sqlite:///{tmp_path/'seed.db'}"
    Base.metadata.create_all(get_engine(url))
    return get_session_factory(url)

def _count(sf, model):
    with sf() as s:
        return s.scalar(select(func.count()).select_from(model))

def test_seed_is_idempotent(tmp_path):
    sf = _fresh(tmp_path)
    seed_all(sf)
    counts1 = {m: _count(sf, m) for m in (models.Country, models.Airline, models.Airport,
        models.City, models.Hotel, models.Place, models.Tip, models.Visa, models.FxRate)}
    seed_all(sf)  # re-run
    counts2 = {m: _count(sf, m) for m in counts1}
    assert counts1 == counts2 and all(v > 0 for v in counts1.values())

def test_seed_preserves_tip_ids(tmp_path):
    sf = _fresh(tmp_path); seed_all(sf)
    with sf() as s:
        ids = s.scalars(select(models.Tip.id).where(models.Tip.scope == "country")).all()
    assert any(i.startswith("tip_country_") for i in ids)

def test_seed_fills_hotel_country(tmp_path):
    sf = _fresh(tmp_path); seed_all(sf)
    with sf() as s:
        assert all(c for c in s.scalars(select(models.Hotel.country)).all())
```

- [ ] **Step 2: Run → fail** (`app.db.seed` missing).
- [ ] **Step 3: Write `app/db/seed.py`.** `seed_all(session_factory)` imports the raw `app/data` modules (their import-time guards fire here), maps each record to the ORM model, and `session.merge()`-es it (portable idempotent upsert). Key mappings:
  - Country ← `COUNTRIES` (direct).
  - Airline ← `enumerate(AIRLINES)` → set `position=i`, `color=AIRLINE_COLORS.get(code)`.
  - Airport ← `AIRPORTS.items()` → `iata=key`, fields + `country_code` (already filled by airports.py).
  - City ← `CITIES`; set `country_code` via reverse lookup from `COUNTRIES` (name→code).
  - **Hotel ← `HOTELS`** — `country` is **already present** on every record (filled at import in `hotels.py`), so map it straight from the record. Map all 21 fields.
  - Place ← `PLACES` (direct).
  - **Tip ← iterate `COUNTRY_TIPS`/`CITY_TIPS` preserving list order**, replicating `tip_service._build_tips` exactly: port its `_slug` helper (`tip_service.py:33-34`) for the `{prefix}`, use `id=f"tip_{scope}_{slug}_{i:02d}"` with `position=i` from `enumerate(records)`, and the `r.get("is_essential", False)` default. Also seed `CountrySummary` ← `COUNTRY_SUMMARIES`.
  - Visa ← `COUNTRY_VISA.items()`.
  - Fx ← `RATES`+`CURRENCY_NAMES` → `FxRate(code,rate,name)`; `COUNTRY_CURRENCY` → `CountryCurrency`; `FxMeta(id=1, last_updated=LAST_UPDATED)`.
  - **Short-code collision guard moves here:** after seeding hotels/places, build the short_code index over the seeded Pydantic models and raise on collision (port `hotel_service._build_short_code_index` / place equivalent). Wrap in a `seed_all` post-check.
  - Commit once at the end (or per-entity). `merge` makes re-runs no-ops.
- [ ] **Step 4: Run → pass.** Then `ruff`.

### Task C2: Wire seeding into lifespan, Makefile, conftest

**Files:** `app/core/lifespan.py`, `Makefile`, `tests/conftest.py`.

- [ ] **Step 1:** `lifespan.py` — **ordering is critical.** The sequence MUST be: (1) ensure schema (existing `create_all` on sqlite; Alembic on Postgres), (2) `seed_all(get_session_factory(settings.database_url))`, (3) `check_city_coverage()`, (4) service `init_db()`. Today `check_city_coverage()` runs at line ~39 BEFORE init — move `seed_all` to run **before** it, because in Chunk E2 `check_city_coverage` becomes DB-backed and on a fresh Postgres (where lifespan does NOT `create_all`) it would otherwise run against an empty/unseeded DB and raise. Seeding is idempotent (merge) so re-runs are safe.
- [ ] **Step 2:** `Makefile` — add:

```makefile
seed:           ## Seed the configured DATABASE_URL from app/data
	.venv/bin/python -c "from app.db.engine import get_session_factory; from app.core.config import get_settings; from app.db.seed import seed_all; seed_all(get_session_factory(get_settings().database_url))"
```

- [ ] **Step 3:** `tests/conftest.py` — in the session-scoped `client` fixture, after the services build the schema, call `seed_all(get_session_factory(tmp_db))` so the test DB has reference data. (The temp-SQLite path; for the `TEST_DATABASE_URL` Postgres path it also runs.)
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/ -q` → green (nothing reads the seeded tables yet; this just proves seeding doesn't break startup/tests). `make test-docker` → green on Postgres.

---

## Chunk D: Per-entity repos (read paths)

> Each repo file in `app/crud/` takes a `session_factory`, returns Pydantic response models, and follows the brief's three techniques (SQL exact/range; Python fuzzy over `SELECT DISTINCT` candidates; Python JSON-list refine). Build them BEFORE migrating consumers (Chunk E) so each consumer swap is a small, green step. Repos are covered by `tests/crud/test_reference_repos.py`.

### Task D1: Simple lookup repos — country, airline, airport, visa, fx

**Files:** Create `app/crud/{country,airline,airport,visa,fx}.py`; Test `tests/crud/test_reference_repos.py`.

- [ ] **Step 1:** Write tests asserting each repo returns the same data the current module-level structures do (e.g. `airlines_repo.list()` returns airlines in `AIRLINES` order; `airport_repo.get("DAD")` matches; `fx_repo.rate("VND")` matches `RATES["VND"]`; `visa_repo.get("Vietnam")` matches). Use a seeded temp-sqlite session factory.
- [ ] **Step 2:** Implement. Pattern (airline, **determinism-critical ordering**):

```python
from sqlalchemy import select
from app.db import models

class AirlineRepository:
    def __init__(self, session_factory): self._sf = session_factory
    def list(self) -> list[dict]:
        with self._sf() as s:
            rows = s.scalars(select(models.Airline).order_by(models.Airline.position)).all()
            return [{"code": r.code, "name": r.name} for r in rows]   # shape flight_service expects
    def color(self, code: str) -> str | None:
        with self._sf() as s:
            r = s.get(models.Airline, code)
            return r.color if r else None
```

  Implement `country`, `airport`, `visa`, `fx` analogously. **Field-name mismatches — do NOT use `model_validate(from_attributes=True)` for these; construct the schema explicitly:**
  - **Airport:** the ORM PK is `iata` but the `Airport` schema field is `code` → `Airport(code=r.iata, name=r.name, city=r.city, country=r.country)`.
  - `visa` → `EntryRequirements(...)` from the row; `fx` → `rate(code)`/`name(code)`/`country_currency(country)`/`last_updated()`.
  Return shapes must match what consumers currently consume.
- [ ] **Step 3:** Run tests → pass. `ruff`. Full suite still green (repos unused yet).

### Task D2: Reference repos with fuzzy + JSON filters — city, hotel, place, tip

**Files:** Create `app/crud/{city,hotel_ref,place_ref,tip}.py`; extend `tests/crud/test_reference_repos.py`.

- [ ] **Step 1:** Tests: `city_repo.distinct_names()` returns all city names; `place_repo.search(city=..., category=..., min_rating=...)` matches current `place_service.search_places` results; `hotel_repo.search(city=..., amenities=[...])` matches; fuzzy `city_repo.resolve("da nang")` → "Da Nang"; `tip_repo.for_location(country=..., city=...)` returns tips ordered by position with correct ids.
- [ ] **Step 2:** Implement using the brief's techniques. Example (place search — JSON tags + filters; fuzzy city handled by caller via `distinct`):

```python
from sqlalchemy import select
from app.core.text import best_match
from app.db import models
from app.schemas.place import Place

class PlaceRepository:
    def __init__(self, session_factory): self._sf = session_factory
    def distinct_cities(self) -> list[str]:
        with self._sf() as s:
            return sorted(set(s.scalars(select(models.Place.city)).all()))
    def all(self) -> list[Place]:
        with self._sf() as s:
            return [Place.model_validate(r, from_attributes=True)
                    for r in s.scalars(select(models.Place)).all()]
    def search(self, *, city=None, category=None, min_rating=None,
               price_level=None, price_level_max=None, recommended=None) -> list[Place]:
        stmt = select(models.Place)
        if city is not None:        stmt = stmt.where(models.Place.city == city)
        if category is not None:    stmt = stmt.where(models.Place.category == category.lower())
        if min_rating is not None:  stmt = stmt.where(models.Place.rating >= min_rating)
        if price_level is not None: stmt = stmt.where(models.Place.price_level == price_level)
        if price_level_max is not None: stmt = stmt.where(models.Place.price_level <= price_level_max)
        if recommended:             stmt = stmt.where(models.Place.is_recommended.is_(True))
        with self._sf() as s:
            return [Place.model_validate(r, from_attributes=True) for r in s.scalars(stmt).all()]
```

  - **city**: `distinct_names()`, `get(name)`, and `list_with_counts()` — note the `City` schema **requires `hotel_count`**, which is NOT an ORM column → the repo must construct `City(name=..., country=..., airport_codes=..., latitude=..., longitude=..., hotel_count=<from hotel_repo.count_by_city()>)` explicitly. Do NOT `model_validate` City.
  - **hotel_ref**: `search(city, min_stars, max_price, amenities)` — SQL for city/stars/price, then **Python refine** the `amenities` all-contains predicate over the fetched rows (portable). `get(id)` + `by_short_code(code)` (build models, match computed `short_code`). Preserve `available_rooms` determinism by returning the same `Hotel` model (with verbatim `id`).
  - **tip**: `for_location` returns `[Tip(...)]` ordered by `position`; `all_tips()` merges country+city; `country_summary(country)`.
  - `Place.model_validate(row, from_attributes=True)` is fine (all required fields are columns; computed `short_code` derives from `id` → identical). The repo does **exact/range filters only**; the **fuzzy city resolution and the result sort stay in `place_service`** (Chunk E4) — the repo's `search` takes an already-resolved exact city.
- [ ] **Step 3:** Run → pass. `ruff`. Full suite green.

---

## Chunk E: Migrate consumers entity-by-entity (suite green after each)

> One task per consumer cluster. After each, run the full suite. **Reference the research brief's call-site inventory for exact line numbers.**
>
> **Module-singleton test-isolation (do this for EVERY migrated service — highest practical regression risk).** Services hold import-time singletons built from `get_settings().database_url`, but tests run against `tmp_db`, and these are NOT FastAPI dependencies (so `dependency_overrides` won't reach them — same trap as `flight_service.set_index_repo` / `saved_place_service._saved_place_service`). For each migrated service, expose a `set_<entity>_repo(repo)` setter (or have the singleton read the URL lazily per call). Then in `tests/conftest.py`, **after** `seed_all(tmp_db)`, repoint every one of them to `get_session_factory(tmp_db)`: `airline`, `airport`, `country`, `city`, `hotel`, `place`, `tip`, `visa`, `fx`. Enumerate each in the task below as you migrate it. A repo left pointed at the real `travel.db` reads stale/unseeded data and fails tests non-obviously.

### Task E1: airports + airlines + fx + visa (simple lookups)
**Files:** `app/services/{airport,flight,currency,visa,board}_service.py`, `app/routers/dashboard.py`.
- [ ] Replace `_AIRPORTS`/`_BY_CODE` (airport_service), `AIRLINES`/`AIRLINE_COLORS` (flight_service, board_service, dashboard), `RATES`/`CURRENCY_NAMES`/`COUNTRY_CURRENCY` (currency_service), `COUNTRY_VISA` (visa_service, dashboard) with repo calls. **flight_service: `airlines_repo.list()` must preserve order** (repo `ORDER BY position`). Run suite → green; `make test-docker` → green.

### Task E2: cities + countries
**Files:** `app/routers/cities.py`, `app/services/{destination,routing}_service.py`, `app/core/invariants.py`.
- [ ] Replace `_ALL_CITIES`/`_BY_NAME`/`_COUNTRIES`/`_HOTEL_COUNTS` (cities router builds `City` incl. `hotel_count` → now from `city_repo` + `hotel_repo.count_by_city()`), `CITIES` fuzzy in destination/routing (`city_repo.distinct_names()` + `best_match` then `city_repo.get(name)`), and `check_city_coverage` (query hotel/place counts per city from repos). Suite + docker → green.

### Task E3: hotels
**Files:** `app/services/hotel_service.py`, `app/routers/cities.py` (hotel counts), `app/routers/dashboard.py` (hotel page).
- [ ] Replace `_HOTELS`/`_HOTEL_CITIES`/`_HOTELS_BY_SHORT_CODE` with `hotel_repo`. Keep `available_rooms` MD5 logic (operates on the returned `Hotel.id`). Suite + docker → green.

### Task E4: places + tips
**Files:** `app/services/{place,tip}_service.py`, `app/routers/dashboard.py` (places/tips pages).
- [ ] Replace `_PLACES`/`CATEGORIES`/`CITIES`/short-code index (place_service) and `COUNTRY_TIPS`/`CITY_TIPS`/`COUNTRY_SUMMARIES`/`_build_tips` (tip_service) with `place_repo`/`tip_repo`. **`place_service.search_places` must KEEP its current shape:** fuzzy `resolve_city` (now over `place_repo.distinct_cities()` + `best_match`) → pass the resolved exact city to `place_repo.search(...)` → apply the existing **sort block** in the service (the repo does not sort). `CATEGORIES`/`CITIES` derived lists come from `place_repo` distinct queries. Tip ids come from the DB (`position`-derived) — assert a known id (e.g. `tip_country_vietnam_00`) is unchanged. Repoint `place`/`tip` repo singletons in conftest. Suite + docker → green.

### Task E5: final consumer sweep
- [ ] `grep -rn "from app.data" app/services app/routers app/core` → only legitimately-remaining uses are `app/db/seed.py` and the `app/data` guards. (Some dashboard aggregations may keep reading `app.data` only if they're purely presentational and not entity reads — justify any remaining import in the commit.) Full suite + `make test-docker` → green.

---

## Chunk F: Determinism + seed tests, docs

### Task F1: Golden determinism test
**Files:** Create `tests/db/test_determinism.py` (uses the `tests/db/fixtures/golden_*.json` captured in Task A0).
- [ ] **Step 1:** Assert post-migration output **byte-equals the A0 golden fixtures** for the exact same queries (`/flights/search?origin=SGN&destination=HAN&departure_date=2026-09-01`; `/hotels/{fixed id}/availability?check_in=2026-09-01&check_out=2026-09-04`). This is the real proof the airline-order + UUID invariants survived the migration (the fixtures were captured on the clean pre-migration tree). Also assert the within-run stability (call twice → identical) and that flight airline assignments follow `AIRLINES` seed order.
- [ ] **Step 2:** Run on SQLite **and** real Postgres (via test-compose) → both match the golden fixtures. If they differ, a determinism invariant broke (most likely airline ordering) — fix before proceeding.

### Task F2: Docs + CLAUDE.md
**Files:** `README.md`, `CLAUDE.md`.
- [ ] Update CLAUDE.md "Seed data" + "Architecture" notes: the 9 entities are now DB-backed (seeded idempotently from `app/data`, which remains the guarded source of truth); reads go through `app/crud` repos per request; `make seed`. Note the `models.` namespace convention and that `app/data` guards still run at seed time. README: add `make seed` + a note that the DB is seeded automatically on startup. Update any stale counts.

---

## Final Verification (Definition of Done)

- [ ] Full suite green on SQLite (re-baselined count) and on real Postgres (`make test-docker`).
- [ ] `alembic upgrade head` (0001+0002) / `downgrade base` / `upgrade head` round-trips on Postgres; `alembic check` no-drift.
- [ ] Seeder idempotent (run twice → identical counts); tip ids + hotel.country verified.
- [ ] Determinism test green on both engines (airline order + UUID invariants held).
- [ ] `grep -rn "Row\b" app/db tests | grep -i "models import\|[A-Za-z]Row("` → empty (rename complete).
- [ ] `grep -rn "from app.data" app/services app/routers app/core` → only `seed.py` (+ justified presentational uses).
- [ ] No public API response shape changed (operationIds test + existing API tests green).
- [ ] CLAUDE.md/README updated; `/compound` decision recorded (per high-risk route).
- [ ] `SUMMARY.md` `### Verify` filled with this evidence.

## Status Log
- 2026-06-19 — plan written (proposed).
