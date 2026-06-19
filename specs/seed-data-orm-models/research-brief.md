# Research Brief — seed-data-orm-models

> **Depth: Deep** (data migration, 9 new tables, multi-domain, new Alembic revision).
> ⚠️ **xia2 `PROJECT.md` is stale** — it describes the upstream `harness-skills` meta-repo, not this
> FastAPI backend; its signal mappings were not used. Depth is Deep on universal signals regardless.
> Recommend re-running `/bootstrap-xia2`.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Build from scratch, reusing existing rails**: new ORM models + per-entity repos + seeder, but reuse (a) the docker-postgres repo/session-factory pattern, (b) the existing `app/schemas/` Pydantic models as repo return types, (c) `core/text.py` for fuzzy, (d) `session.merge()` for portable idempotent seeding. |
| **Why lightest credible path** | No seed-to-DB infra exists, so the models/repos/seeder are genuinely new — but every supporting rail already exists and is proven on this branch. |
| **Confidence** | 80% |
| **Next step** | `/writing-plans`. Mind the **two determinism traps** below before coding. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Stack | Python 3.10+, FastAPI, Pydantic v2, **SQLAlchemy 2.0.51 (sync)**, psycopg 3, Alembic 1.18 |
| DB | Dual-engine: `sqlite:///travel.db` (default/tests) · `postgresql+psycopg://…` (Docker). Engine from `DATABASE_URL`. |
| Existing ORM | `app/db/models.py` — Booking/Trip/TripItem/TripPlaceLink/SavedPlace/FlightIndex (to be renamed off `Row` + split into a package). Repos in `app/crud/` take a `session_factory`; return Pydantic models. |
| Seed data | `app/data/*.py` — 9 raw-dict modules + import-time consistency guards (validate vs `countries.py`). |
| Constraints | CLAUDE.md: deterministic-from-seed generation, stable UUIDs, append-only positional tip IDs, `countries.py` source-of-truth; public response models = FE TS-codegen contract. |

## ⚠️ Determinism traps (must design around — would silently corrupt output)

1. **Airline list ORDER feeds the flight generator.** `flight_service.generate_flights` does
   `rng.choice(AIRLINES)` with a **seeded** RNG (`Local` flight_service.py ~line 102). `rng.choice`
   indexes into the list, so if the DB returns airlines in a different order than the `AIRLINES` seed
   list, a *different airline* is chosen → flight data changes → determinism broken. **The `Airline`
   model needs a `position` column and the repo MUST `ORDER BY position`** so `airlines_repo.list()`
   reproduces the seed-list order byte-for-byte. (Same discipline as Tip's positional IDs.) This is
   the single highest-risk item in the migration.
2. **`hotel.country` is derived at runtime, not stored.** `hotels.py` records carry only `city`;
   `country` is filled by a city→country lookup, and tests assert it
   (`test_hotels.py:54 test_list_hotels_country_matches_city`, `:49 country_is_non_empty`). **The
   seeder must populate `hotel.country`** from the city lookup at seed time (same source as today).
   `hotel.id-check_in-check_out` MD5 (`available_rooms`) and `flight.id` MD5 (`board_service._hash`)
   use stable IDs — fine as long as UUIDs are stored/serialized as identical strings.

## Local Findings — exact column inventory (from a full call-site sweep)

Columns the ORM tables must carry (superset of what consumers read; `Local`):

- **Country** (`countries.py`): name, code(PK), region, latitude, longitude.
- **Airline** (`airlines.py`): code(PK), name, **position** (new — order), color (from `AIRLINE_COLORS`, nullable; default `AIRLINE_COLOR_DEFAULT` applied in serialization).
- **Airport** (`airports.py`, dict keyed by IATA): iata(PK), name, city, country, country_code (derived from `countries.py` at seed time).
- **City** (`cities.py`): name, country(name), country_code(derived), airport_codes(JSON list), latitude, longitude. Unique (name,country).
- **Hotel** (`hotels.py` — RICH, enumerate ALL): id(UUID PK), code, name, city, **country(derived at seed)**, address, star_rating, price_per_night, currency, amenities(JSON), image_url, rating, review_count, description, property_type, chain, check_in_time, check_out_time, breakfast_included(bool), free_cancellation(bool), languages_spoken(JSON). short_code is a derived `@property` (not stored).
- **Place** (`places.py`): id(UUID PK), name, city, country, category, description, address, rating, review_count, price_level, opening_hours, image_url, tags(JSON), is_recommended(bool), latitude, longitude. short_code derived.
- **Tip** (`tips.py`): id(PK=`tip_{scope}_{prefix}_{NN}`), scope(country|city), key, position(int), category, title, content, is_essential(bool). + **CountrySummary**(country PK, summary).
- **Visa** (`visa.py`): country(PK), visa_free_days, visa_on_arrival(bool), e_visa(bool), passport_validity_months, summary.
- **Fx** (`fx.py`): **FxRate**(code PK, rate, **name** ← from `CURRENCY_NAMES`), **CountryCurrency**(country PK, code), **FxMeta**(last_updated). *Design note: `CURRENCY_NAMES` was missed in design.md — fold `name` into FxRate.*

### Consumer call-site inventory (~15 — every site to migrate)

Module-level caches to remove / repoint (built from `app.data` at import):
- `routers/cities.py`: `_HOTEL_COUNTS`, `_ALL_CITIES`, `_BY_NAME`, `_COUNTRIES` (L20-41).
- `routers/dashboard.py`: raw imports `AIRLINE_COLORS/CITIES/COUNTRIES/COUNTRY_TIPS/COUNTRY_VISA`; `_CITY_COUNTRY` (L389); `_tip_destinations`/`_visa_destinations` iterate `_COUNTRIES`.
- `airport_service`: `_AIRPORTS`, `_BY_CODE`. `hotel_service`: `_HOTELS`, `_HOTEL_CITIES`, `_HOTELS_BY_SHORT_CODE`. `place_service`: `_PLACES`, `CATEGORIES`, `CITIES`, `_PLACES_BY_SHORT_CODE`. `tip_service`/`visa_service`: `_ALL_CITIES`/`_ALL_COUNTRIES`. `currency_service`: `_COUNTRY_NAMES`.

Access patterns by site: exact dict/code lookup (airport by IATA, fx by code, visa/tips by country), fuzzy `best_match` over candidate lists (destination/routing/place/hotel/visa/tip/currency — city/country resolution), list+filter (place/hotel search), aggregation (cities hotel-counts, dashboard tip/visa destination grids, `invariants.check_city_coverage`).

**Short-code collision guards** (`hotel_service._build_short_code_index`, `place_service`) currently raise at import on a duplicate derived short_code — must run at **seed time** instead (over DB rows) so the guarantee survives.

## Local Findings — tests & guards to preserve

- **Tests importing `app.data` directly** still work because `app/data/*` is **kept** as the seed source: `test_hotels.py` (`country_by_city` from `CITIES`), `test_currency.py`, `test_visa.py`.
- **Behavioral asserts to keep green:** hotel.country non-empty + matches city (`test_hotels.py:49,54`); availability ≥0 + deterministic (`test_hotel_availability.py`); operationIds unique; currency cross-rate; visa lookup.
- **Import-time guards** (must not weaken; `Local`): `cities.py:381`, `airports.py:~273` (KeyError fill country_code), `places.py:4239-4270` (3 guards), `tips.py:766-773` (unknown + coverage-equality), `visa.py:126-130`, `fx.py:83-93` (country→code→rates→names chain). These run on import-for-seeding → intact. Optionally mirror as FK constraints (second layer).

## Docs / Upstream Findings

- **Idempotent seeding — `session.merge()` is the portable choice** (`Docs`): semantics match INSERT-on-conflict but it is **backend-agnostic** (SELECT + INSERT/UPDATE by PK), identical on SQLite + Postgres. SQLAlchemy 2.0 has **no** backend-agnostic upsert construct; `on_conflict_do_update` is faster but dialect-specific (we already branch SQLite/PG for `flight.remember_many`). At seed scale (hundreds–low thousands of rows, once at startup) `merge()` per row is simple, correct, and idempotent → **recommended**. Use the dialect `on_conflict` only if startup seeding proves slow.
- Repo/session pattern, dual-engine, JSON column type, partial indexes, Alembic autogenerate+`alembic check` are all proven on this branch (PR #11) — reuse verbatim.

## Recommendation

Build the 9 ORM models (+CountrySummary, +FxRate/CountryCurrency/FxMeta) in `app/db/models/` (plain
names, `models.` namespace to avoid the Pydantic collision), per-entity repos in `app/crud/` returning
the existing schemas, an `app/db/seed.py` using `session.merge()` from `app/data` (kept as guarded
source), wired into lifespan + `make seed` + the test fixture, behind Alembic `0002`. Reuse rails;
don't reinvent. **Why not "keep in memory":** the user chose per-request DB reads — honored, with
fuzzy/JSON refined in Python over DB-fetched candidate sets.

## Risks / Unknowns / Follow-ups

- **Airline ordering (determinism)** — highest risk; `position` column + `ORDER BY` (above).
- **`hotel.country` seed-fill** — must replicate the runtime city→country derivation.
- **FK-by-name** (`city.country`→`country.name`): sound but requires a unique index on `country.name`
  (names are unique in `countries.py`). Acceptable; alternatively rely on the retained import guards +
  a denormalized `country_code`. Plan should pick one and state it.
- **Per-request perf**: hotels (~hundreds) / places (~hundreds) lists fetched per search + Python
  refine — fine at this scale; revisit only if measured.
- **Blast radius**: ~15 consumers; migrate per entity keeping the suite green each step.
- **Follow-ups for the plan (max 2):** (1) confirm `make seed`/lifespan seeding is idempotent under
  re-run on a non-empty Postgres (merge handles it); (2) decide FK-by-name vs denormalized-code.

## Source Pack

- Local: `app/data/*.py` (+ guards at the cited lines), `app/services/{flight,hotel,place,airport,destination,routing,visa,currency,tip,board}_service.py`, `app/routers/{cities,dashboard}.py`, `app/core/{invariants,text}.py`, `app/crud/booking.py`, `tests/api/hotel/test_hotels.py`, `tests/api/info/test_{currency,visa}.py`, `specs/seed-data-orm-models/design.md`.
- Docs: https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html (ORM INSERT/on-conflict), SQLAlchemy discussion #9675 (merge vs on_conflict for idempotent upsert).

## Evidence Boundary

> **Confirmed from code:** column inventories, the ~15 call sites + their access patterns, the
> determinism seeds (airline-order, hotel.id/flight.id MD5), the import-time guards, the tests that
> import `app.data`, the proven repo/dual-engine/Alembic rails.
> **Inferred:** `session.merge()` perf is adequate at seed scale (not load-tested); FK-by-name is
> sound given unique country names.
> **Not checked:** exact per-request latency under Postgres for the largest list endpoints (places/
> hotels) — expected fine, measure if needed.
