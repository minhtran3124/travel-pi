# Design — seed-data-orm-models

**Status:** approved (brainstorming, 2026-06-19)
**Lane:** high-risk (see SUMMARY.md)
**Depends on:** `feat/docker-postgres-setup` (PR #11) — dual-engine SQLite/Postgres ORM + Alembic.

## Goal

Persist the 9 read-only seed entities in `app/data/` into the database via SQLAlchemy ORM,
restructure `app/db/models.py` into a per-entity package, and serve them through **per-request
DB queries** — without breaking the public API contract, the deterministic generation invariants,
or the 621-test parity suite.

## Decisions (locked in brainstorming)

| Fork | Decision |
|---|---|
| Read path | **Per-request DB queries** (data is live/editable via the DB). |
| Fuzzy / JSON-list filters | **Keep in Python** — SQL does exact/range; `core/text.py` fuzzy-resolves over distinct candidate sets; amenities/airport_codes list-predicates refine in Python after a coarse SQL filter. Portable SQLite+Postgres. |
| Seeding | **Idempotent upsert** from `app/data` → DB, run on startup (after migrations) + `make seed` + test session fixture. |
| `app/data/*.py` | **Kept as the seed SOURCE** — preserves `countries.py` source-of-truth + import-time consistency guards (not weakened). |
| Schemas | `app/schemas/` response models **stay the public contract** (no breaking changes); repos map ORM→response models. |
| Write side | **Read-only now**; data editable directly in the DB (no new write endpoints this initiative). |
| Branch | Stack on `feat/docker-postgres-setup` as `feat/seed-data-orm-models`; Alembic `0002_seed_entities`. |

## Architecture

### 1. Model package — `app/db/models/`
Split the single `app/db/models.py` into a package, one file per entity, `__init__.py` re-exports
all classes so `Base.metadata` (Alembic autogenerate + `create_all`) sees them unchanged.

```
app/db/models/
  __init__.py          # re-exports every model class
  booking.py           # Booking            (moved from models.py)
  trip.py              # Trip, TripItem, TripPlaceLink (moved)
  saved_place.py       # SavedPlace         (moved)
  flight_index.py      # FlightIndex        (moved)
  country.py           # Country            (new — source of truth)
  airline.py           # Airline            (new)
  airport.py           # Airport            (new)
  city.py              # City               (new)
  hotel.py             # Hotel              (new)
  place.py             # Place              (new)
  tip.py               # Tip                (new)
  visa.py              # Visa               (new)
  fx.py                # FxRate, CountryCurrency, FxMeta (new)
```

**Naming & the ORM-vs-Pydantic collision (per user request: no `Row` suffix).** ORM model classes
are named plainly — `Booking`, `Hotel`, `Place`, `City`, `Airport`, `Tip`, `Country`, … — which
**collide by name** with the existing Pydantic response schemas in `app/schemas/` (`Hotel`, `Place`,
`City`, …). Resolve the collision by **namespace, not by suffix**:

- **ORM models** are always referenced through the package namespace:
  `from app.db import models` → `models.Hotel`, `models.Booking`, `session.get(models.Hotel, id)`.
- **Pydantic schemas** are imported directly: `from app.schemas.hotel import Hotel`.
- In a repo file (`app/crud/hotel.py`) that needs both, the ORM side reads `models.Hotel` and the
  API side reads `Hotel` — visually unambiguous, no aliases. (If a file ever finds a direct ORM
  import clearer, alias it `from app.db.models.hotel import Hotel as HotelModel` — never reintroduce
  a `Row`/`ORM` suffix on the class definition itself.)
- The `__init__.py` re-exports the plain class names so `models.Hotel` resolves.

**This renames the 6 already-shipped ORM classes** from the docker-postgres work
(`BookingRow→Booking`, `TripRow→Trip`, `TripItemRow→TripItem`, `TripPlaceLinkRow→TripPlaceLink`,
`SavedPlaceRow→SavedPlace`, `FlightIndexRow→FlightIndex`) and updates their references in
`app/crud/{booking,trip,saved_place,flight}.py`, `tests/conftest.py`, `tests/test_db_models.py`, and
`alembic/env.py`. It is a **class-rename only** — `__tablename__` values and all column definitions
are unchanged, so the DB schema, the `0001_initial` migration, and `alembic check` (no-drift) are
unaffected. Moving the classes into the package is otherwise import-only churn.

### 2. New ORM tables (columns mirror the seed dicts; FKs encode current guards)

- **Country** — `code` PK, `name`, `region`, `latitude`, `longitude`.
- **Airline** — `code` PK, `name`, **`position` int** (preserves the `AIRLINES` seed-list order — **load-bearing for determinism**: `flight_service.generate_flights` does `rng.choice(AIRLINES)` over a seeded RNG, so the repo MUST `ORDER BY position` to reproduce the same airline picks byte-for-byte), `color` (nullable; from `AIRLINE_COLORS`, default `AIRLINE_COLOR_DEFAULT` applied in serialization).
- **Airport** — `iata` PK, `name`, `city`, `country`, `country_code` FK→`country.code`.
- **City** — surrogate `id` PK, `name`, `country` (the country **name** string, exactly as `cities.py` stores it), `country_code` (denormalized from `countries.py` for convenience, nullable), `airport_codes` JSON, `latitude`, `longitude`. Unique `(name, country)`. The country link is by **name** (matching the current code, which resolves a city's country by name); a FK is enforced against `Country.name` (add a unique index on `country.name`) — *not* against `code`. Seeding note: `City.country` ← the dict's `country` field (name); `country_code` ← reverse-looked-up from `countries.py`.
- **Hotel** — `id` UUID PK (seeded verbatim), `code`, `name`, `city`, `country`, `address`, `star_rating`, `price_per_night`, `currency`, `amenities` JSON, + remaining fields.
- **Place** — `id` UUID PK (seeded verbatim), `name`, `city`, `country`, `category`, `description`, `address`, `rating`, `review_count`, `price_level`, `opening_hours`, `image_url`, + remaining fields.
- **Tip** — one row per tip (normalized, not JSON lists). `id` PK = the positional id
  `tip_{scope}_{prefix}_{NN}` exactly as `tip_service._build_tips()` derives it today; `scope`
  (`country`|`city`), `key` (country **or** city name, from `COUNTRY_TIPS`/`CITY_TIPS` keys),
  `position` int, `category`, `title`, `content`, `is_essential`. Unique `(scope, key, position)`.
  **ID-preservation invariant:** the seeder MUST insert tips in the exact list order of
  `COUNTRY_TIPS[key]` / `CITY_TIPS[key]` so `position` (and thus the derived `id`) matches the
  current runtime IDs — honoring the `tips.py` "append only, never reorder" rule. The `tip_service`
  ID-building logic moves into the seeder; the repo reads rows back ordered by `position`.
- **CountrySummary** — `country` PK, `summary` (from `COUNTRY_SUMMARIES`).
- **Visa** — `country` PK, `visa_free_days`, `visa_on_arrival`, `e_visa`, `passport_validity_months`, `summary`.
- **Fx** — `FxRate` (`code` PK, `rate`, `name` ← from `CURRENCY_NAMES`), `CountryCurrency` (`country` PK, `code`), `FxMeta` (`last_updated`).
- **Hotel.country (seed-fill):** `hotels.py` records carry only `city`; `country` is derived at runtime today and asserted by tests. The **seeder must populate `Hotel.country`** via the city→country lookup at seed time (same source as the current runtime derivation).

All JSON columns use the portable `JSON` type (matches the docker-postgres decision — no JSONB).

### 3. Read path — per-request repos (`app/crud/<entity>.py`)
Each repo takes a `session_factory` (the established pattern) and exposes the queries its service
needs, returning **Pydantic response models** (the `app/schemas/` classes) — ORM stays inside crud.

Three portable techniques:
1. **Exact / range / sort** → SQLAlchemy `select().where().order_by()`.
2. **Fuzzy free-text resolution** (e.g. resolve a user's city string): repo runs
   `SELECT DISTINCT <col>` (small set), calls `core/text.py best_match`/`fuzzy_filter` in-memory to
   pick the canonical value, then queries by exact value. Fuzzy logic unchanged.
3. **JSON-list predicates** (amenities all-contains, airport_codes): coarse SQL filter (city/stars/
   price) → fetch → refine the list predicate in Python. Acceptable at seed scale.
4. **Derived `short_code`**: repo builds the Pydantic model; its `@property` computes the code.
   Lookup-by-short-code resolves over the candidate set as today.

### 4. Seeding — `app/db/seed.py`
- `seed_all(session_factory)` performs **idempotent upsert** of every entity from `app/data/*`
  (the source of truth) keyed by PK/code/stable-id (`session.merge` or dialect upsert). Re-runnable.
- Invoked: (a) lifespan startup after `create_all`/migrations; (b) `make seed`; (c) the pytest
  session fixture (after schema creation).
- `app/data/*.py` import-time guards run when the module is imported for seeding — guards intact.

### 5. Consumer migration (~15 sites)
Each service/router that currently imports `from app.data.X import …` and iterates module-level
lists switches to calling the matching repo. The module-level `_PLACES = [Place(**r) for r in PLACES]`
caches are removed; `place_service`/`hotel_service` etc. query per request. Routers/`invariants.py`/
`dashboard.py` updated to the repos. `core/invariants.check_city_coverage` runs its checks via repo
queries at startup.

**Fuzzy-resolution migration pattern (explicit).** Services that build module-level candidate lists
for `core/text.py` (e.g. `destination_service` `best_match(city, CITIES)`, `currency_service`
`best_match(country, _COUNTRY_NAMES)`, `visa_service` `best_match(city, _ALL_CITIES)`,
`hotel_service`/`place_service` `_HOTEL_CITIES`/`CITIES`) change to: **fetch the distinct candidate
set from the repo at resolution time** (e.g. `cities_repo.distinct_city_names()`), pass it to
`best_match`/`fuzzy_filter` in Python, then query the repo by the resolved exact value. The repo owns
the candidate-fetch query (`SELECT DISTINCT`); the service owns the fuzzy call. Acceptable at seed
scale (tens–hundreds of distinct values).

**Consumer inventory (~15):** `routers/cities.py`, `routers/dashboard.py`, `core/invariants.py`,
and services `destination`, `flight`, `airport`, `routing`, `place`, `visa`, `currency`, `hotel`,
`board`, `tip`. The dashboard router currently aggregates several module-level dicts
(`AIRLINE_COLORS`, `CITIES`, `COUNTRIES`, `COUNTRY_TIPS`, `COUNTRY_VISA`) for its HTML — these become
repo calls assembled in the router (or a small read-only aggregation helper); behavior unchanged.

### 6. Determinism (must not change)
Flight + hotel-availability generators read airline/airport/hotel **values** from the DB but the
MD5 seeds (`hotel.id-check_in-check_out`, `origin-dest-date`) and the seeded UUIDs are byte-identical
to today → generated output unchanged. **UUID-serialization invariant:** UUIDs are stored as
**strings** (the ORM `id` column is `String`, seeded verbatim from the existing UUID5 string values),
so the repo-built Pydantic model's `hotel.id` is the same string (same casing/hyphenation) that the
in-memory dict produced — the MD5 input is identical. Guarded by both the existing suite staying green
**and** a new explicit determinism test (§Testing) comparing generator output for a fixed query
pre/post migration (golden values).

## Components & boundaries

- **ORM models** (`app/db/models/*`) — schema only, no logic.
- **Repos** (`app/crud/*`) — all SQL + Python-side fuzzy/JSON refinement; return Pydantic models.
- **Services** — business rules, call repos (no direct `app/data` imports for the migrated entities).
- **Seeder** (`app/db/seed.py`) — one-way `app/data` → DB upsert.
- **`app/data/*`** — unchanged seed source + guards.
- **`app/schemas/*`** — unchanged public response contract.

## Testing strategy

- Parity gate: the full suite (621) stays green on SQLite **and** real Postgres (`make test-docker`).
- New tests: seeder idempotency (run twice → same row counts); each repo's filters/fuzzy/JSON paths;
  a determinism guard (hotel availability + flight generation identical pre/post migration for a
  fixed query); `alembic check` no-drift after the models package split + `0002` revision.
- Test DB seeded once per session via conftest.

## Risks / mitigations

- **Blast radius (~15 consumers):** migrate per entity, suite green after each — incremental.
- **Public contract drift:** repos return the existing response schemas; no schema field changes.
- **Determinism regression:** explicit pre/post determinism test + existing suite.
- **Guard weakening (hard-gate sensitive):** guards remain in `app/data`; FKs add a second layer.
- **Per-request perf:** seed-data scale is small; acceptable. Revisit caching only if measured.

## Out of scope

- Write/admin endpoints for these entities (separate initiative).
- JSONB / trigram / Postgres-specific query features.
- Changing the public API response shapes.
