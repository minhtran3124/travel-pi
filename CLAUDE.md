# CLAUDE.md

Guidance for Claude Code working in this repo.

## Work in the root project

The real codebase is the **Python FastAPI mock backend at the repo root**
(`app/`, `tests/`, `scripts/`). Run commands from the root, edit the root `app/`.

Ignore the untracked `apps/` and `packages/` monorepo scaffold — it's incomplete,
not buildable, and `apps/api/app/` is a stale copy of the root `app/`. Watch out
for the duplicate `app/` tree and two `travel.db` files so you don't edit the
wrong one.

## What this is

A FastAPI mock backend for a Travel Planner agent: flights, hotels, bookings,
places, tips, weather, cities. Everything is faked (no keys/payments/external
calls) **except** the keyless Open-Meteo calls — `/weather` (Forecast +
Geocoding), `/air-quality` (Air-Quality API), and `/destinations/{city}/climate`
(ERA5 Archive) — and `/*/route` (OpenRouteService, offline haversine fallback).
The three Open-Meteo services share `weather_service._fetch_json`/`geocode_city`.
Current endpoint list lives in `APIS.md`; `mock-api-spec.md` is the original
contract (now stale on layout).

## Run it

Persistence is dual-engine: SQLite by default (local/tests), Postgres in Docker,
selected by `DATABASE_URL`. See `README.md` for the full three-path run guide.

```bash
# Local, on SQLite (zero-config)
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
make dev                                            # uvicorn, Swagger at /docs
make test                                           # 685 tests on SQLite

make seed                                           # re-seed app/data into DATABASE_URL (idempotent; auto-runs on startup)

# Docker + Postgres (migrations run automatically via the entrypoint)
make up                                             # app at :8000, Postgres in a container
make test-docker                                    # 685 tests on isolated Postgres (cross-engine parity)

ruff check app scripts && ruff format app scripts
```

## Layout

```
app/
  main.py        # app factory, CORS, exception handlers, request-log middleware
  exceptions.py  # domain exceptions (AppError + subclasses), no FastAPI deps
  core/          # config, logging, lifespan, geo (haversine), text (fuzzy match)
  routers/       # one file per endpoint group (dashboard.py = HTML, not API)
  services/      # business logic
  repositories/  # SQLAlchemy ORM data access (per-entity repos), no logic
  db/models/     # ORM models package (plain class names, used via `models.` namespace)
  schemas/       # Pydantic v2 models (extend AppBaseModel)
  data/          # seed source of truth + import-time guards (countries, airlines, …)
tests/           # pytest, isolated temp SQLite DB per run (conftest.py)
```

## Architecture rules

- **Layering:** routers → services (rules) → repositories (SQL). Services raise domain
  exceptions (`NotFoundError`→404, `ConflictError`→409, `UpstreamError`→502) and
  never import `HTTPException`. `main.py` turns `AppError`, `HTTPException`, and
  `RequestValidationError` into one JSON envelope
  (`{error, message, status_code, path, [errors]}`). Routes declare codes via
  `responses=error_responses(...)`.
- **Persistence is SQLAlchemy 2.0 ORM (sync) over SQLite-or-Postgres**, chosen
  by `DATABASE_URL` (default `sqlite:///travel.db` for local/tests; Docker
  injects `postgresql+psycopg://...`). Schema is versioned by **Alembic**
  (`alembic upgrade head`, run automatically by the Docker entrypoint). The ORM
  is confined to `app/repositories/` — services/schemas/routers stay ORM-free. ORM models
  live in the **`app/db/models/` package** (one file per entity, plain class
  names like `Hotel`/`City`), referenced via the **`models.` namespace**
  (`from app.db import models` → `models.Hotel`) to avoid colliding with the
  identically-named Pydantic response models in `app/schemas/`.
- **Bookings are the canonical mutable state**; `total_price` is always computed
  server-side — requests never carry a price. `GET /bookings/{id}` accepts the
  UUID or the derived `confirmation_code`; `cancel` is a soft, idempotent state
  change. Trips, saved_places, and the flight_index also persist (same ORM).
- **Deterministic generation, never stored:** flights and hotel availability are
  generated from an MD5 seed (flights: `origin-dest-date`; rooms:
  `hotel.id-check_in-check_out`), so the same query always returns the same
  result and IDs reverse back into search params. **Changing the seed algorithm
  breaks existing IDs.**
- **Async only for real network I/O:** `weather_service` and `routing_service`
  (and their `httpx.AsyncClient`) are async; everything else is sync. Routing
  degrades to an offline haversine estimate with no `ORS_API_KEY` (`source` field
  says which); results are cached in-process.
- **Seed data is DB-backed.** The 9 reference entity groups (countries, airlines,
  airports, cities, hotels, places, tips, visa, fx) live in the database and are
  **read through per-entity repos in `app/repositories/` per request**. `app/data/`
  REMAINS the guarded source of truth — `data/countries.py` is canonical for
  countries and the other data files validate against it; those **import-time
  consistency guards now run at seed time**, so typos still fail loudly on
  startup. `app/db/seed.py` seeds the DB **idempotently** from `app/data` via
  `session.merge()` (City uses a natural-key upsert); seeding runs automatically
  on startup and via `make seed` (seeds the configured `DATABASE_URL`). `from
  app.data` should appear only in `app/db/seed.py`. Determinism: `Airline.position`
  / `Country.position` preserve seed order (airline order is load-bearing for
  seeded flight generation), and tips are positional-ID'd — **append only, never
  reorder** the `app/data` lists.
- Routes return typed `response_model`s so the FE can codegen TS types.

## Conventions

- Python 3.10+ hints (`list[X]`, `X | None`), Pydantic v2.
- `datetime.now(timezone.utc)`, never `utcnow()`.
- `logging.getLogger(__name__)`, never `print()`.
- **Fuzzy name resolution everywhere** free-text city/country is accepted, via
  `core/text.py` (`best_match` / `fuzzy_filter`). Resource IDs (UUIDs, IATA)
  stay exact. An unrecognised city/country returns `count: 0`, not 404.
- Keep it minimal — no auth, pagination, or rate limiting (see
  `mock-api-spec.md` §1). Console logging is in scope; anything heavier is not.
  Persistence uses **SQLAlchemy 2.0 ORM (sync)**, engine selected by
  `DATABASE_URL` (SQLite default for local/tests, Postgres in Docker), schema
  versioned by **Alembic**; **the ORM is confined to `app/repositories/`** —
  services/schemas/routers stay ORM-free. (See `docs/decisions/0001-orm-and-postgres.md`.)

## Design Context

The `/dashboard/*` HTML pages (Jinja2) have a captured design system. Before
UI work on them, read `PRODUCT.md` (strategy: register, users, principles,
anti-references) and `DESIGN.md` (visual: colors, typography, components). The
CSS tokens and component styles live in `app/templates/base.html` (`:root`
variables); it's the single source of truth for the dashboard's look — the v2
**"Sunset"** system: a dark, warm-coral operations board with friendly
per-topic color-coding. `--ink` = primary text, `--accent`/`--accent-2` = coral
(brand voice; bright `--accent` takes dark `--on-accent` text, deep `--accent-2`
takes white), a closed status spectrum (`--green/--yellow/--orange/--cyan/--red`),
and per-card `--c` hues for topic/type color-coding (tips categories, hotel
types). Page-specific styles live in each template's `<style>` block. Use
`/impeccable` for design tasks; `DESIGN.md` documents the full visual system.
