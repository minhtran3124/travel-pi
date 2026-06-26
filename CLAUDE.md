# CLAUDE.md

Guidance for Claude Code working in this repo.

## Project

FastAPI mock backend for a Travel Planner agent. Everything is faked except keyless Open-Meteo calls (`/weather`, `/air-quality`, `/destinations/{city}/climate`) and `/*/route` (OpenRouteService, haversine fallback).

**Monorepo (restructure in progress — `specs/monorepo-fe/`).** The BE now lives under
`apps/api/` (Next.js FE in `apps/web/` is pending — Phase 1+). Do BE work in `apps/api/`
and run BE commands from there. The single Python venv stays at the repo root (`.venv`),
which `apps/api/Makefile` references via `VENV ?= ../../.venv`. Root-level monorepo tooling
(pnpm workspaces + Turborepo, a delegating root Makefile) is not wired up yet.

## Run & Test

```bash
# Setup (once, from repo root)
uv venv && source .venv/bin/activate && uv pip install -r apps/api/requirements.txt

# All BE commands run from apps/api/
cd apps/api
make dev          # uvicorn + hot-reload, Swagger at /docs
make test         # full suite on SQLite (fast, zero-config)
make test-docker  # same tests on Postgres (cross-engine parity)
make seed         # re-seed reference data into DATABASE_URL

# Lint / format (from apps/api/)
ruff check app scripts
ruff format app scripts

# Debug: run a single test file (from apps/api/)
../../.venv/bin/python -m pytest tests/api/trip/test_trip_budget.py -xvs

# Debug: open SQLite shell, check alembic state (from apps/api/)
sqlite3 travel.db
../../.venv/bin/alembic current
../../.venv/bin/alembic upgrade head
```

## Layout

```
apps/api/        # FastAPI backend (relocated from repo root)
app/
  main.py        # app factory, CORS, exception handlers, middleware
  exceptions.py  # domain exceptions (AppError subclasses), no FastAPI deps
  core/          # config, logging, lifespan, geo, text (fuzzy match)
  routers/       # one file per endpoint group
  services/      # business logic
  repositories/  # SQLAlchemy ORM data access only — no logic
  db/models/     # ORM models (plain class names, used via `models.` namespace)
  schemas/       # Pydantic v2 models (extend AppBaseModel)
  data/          # seed source of truth
tests/           # pytest, isolated temp SQLite DB per run
```

## Architecture

- **Layers:** routers → services → repositories. Services raise domain exceptions (`NotFoundError`→404, `ConflictError`→409, `UpstreamError`→502), never `HTTPException`.
- **ORM confined to `repositories/`**. Models live in `app/db/models/`, referenced as `models.Hotel` etc. to avoid collision with Pydantic schemas.
- **Persistence:** SQLite locally, Postgres in Docker — selected by `DATABASE_URL`. Schema versioned by Alembic.
- **Deterministic generation:** flights and hotel availability seeded from MD5 hash; same query = same result. Don't change the seed algorithm.
- **Async only for real I/O:** `weather_service`, `routing_service`. Everything else is sync.
- **Seed data is DB-backed** — seeded idempotently from `app/data/` on startup. `from app.data` appears only in `app/db/seed.py`.

## Conventions

- Python 3.10+ hints, Pydantic v2. `datetime.now(timezone.utc)`, never `utcnow()`.
- Fuzzy name resolution for free-text city/country (`core/text.py`). Unknown city → `count: 0`, not 404.
- `logging.getLogger(__name__)`, never `print()`.
- No auth, pagination, or rate limiting.

## Design (dashboard only)

Before touching `/dashboard/*` templates: read `PRODUCT.md` + `DESIGN.md`. Tokens live in `app/templates/base.html` `:root`. Use `/impeccable` for design tasks.
