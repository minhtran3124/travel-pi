# 0002 — Reference seed data persisted to the database (per-request reads)

**Status:** accepted (2026-06-19)
**Builds on:** [0001-orm-and-postgres](0001-orm-and-postgres.md) (SQLAlchemy ORM, dual-engine SQLite/Postgres, Alembic).

## Context

The 9 reference entity groups (countries, airlines, airports, cities, hotels, places,
tips, visa, fx) lived as read-only Python dicts/lists in `app/data/*.py`, loaded into
in-memory caches at import and read directly by ~15 services/routers. We wanted them
modeled as first-class ORM entities and persisted to the database.

## Decision

- **One ORM model per entity** in an `app/db/models/` **package** (one file per entity).
  ORM classes are named plainly (`Hotel`, `Place`, …) — the `Row` suffix was dropped — and
  disambiguated from the identically-named `app/schemas/` Pydantic response models by the
  **`models.` namespace** (`models.Hotel` vs `Hotel`). This also renamed the 6 entities from
  0001 (class-rename only; tables/migrations unchanged).
- **Per-request DB reads** via per-entity repos in `app/crud/` (the user's choice over an
  in-memory cache). Repos do exact/range filters in SQL and keep **fuzzy matching
  (`core/text.py`) and JSON-list predicates in Python** over candidate sets fetched from the
  DB — portable across SQLite + Postgres, preserving exact prior behavior.
- **`app/data/*.py` is kept as the seed source of truth.** Its import-time consistency guards
  (validate everything against `countries.py`) now run at **seed time**. An idempotent
  `app/db/seed.py` upserts every entity via `session.merge()` (City via a `(name, country)`
  natural-key upsert), run on startup + `make seed` + the pytest fixture. New Alembic revision
  `0002_seed_entities`.
- **Public API response schemas (`app/schemas/`) are unchanged** — repos map ORM rows to the
  existing response models, so the FE TS-codegen contract is stable.

## Consequences / things to remember

- **Determinism is order-sensitive.** `flight_service` does `rng.choice(AIRLINES)` and
  `board_service` does `Random(seed).sample(airports, …)` over seeded RNGs; the flight/hotel
  generators key MD5 on stable IDs. Moving from Python-literal order to DB rows required
  **seed-order `position` columns on Airline, Country, Airport, Hotel, Place** with the repos
  doing `ORDER BY position`, plus golden cross-engine fixtures (`tests/db/test_determinism.py`)
  asserting byte-equal output. **Any new list-read of a reference entity must use a deterministic
  `ORDER BY`** — the every-boot idempotent `merge()` UPDATEs relocate Postgres heap tuples, so
  an unordered SELECT silently drifts (this caused real pagination/board bugs caught in review).
- **Test isolation:** reference repos are module-level singletons (not FastAPI deps), so
  `tests/conftest.py` repoints each via `set_<entity>_repo(...)` to the temp DB after `seed_all`.
- **Env gotcha:** the Docker test container is **Python 3.12 (eager annotations)** while local is
  3.14 (PEP 649 lazy) — a `list`/`dict` builtin-shadow in a module that also uses it as an
  annotation fails only in Docker. Run `make test-docker` before claiming done; add
  `from __future__ import annotations` where needed.
- Reference data is now editable directly in the DB and reflected per request; no write
  endpoints were added (out of scope — a future initiative).

See `specs/seed-data-orm-models/` (SUMMARY, design, research-brief, PLAN).
