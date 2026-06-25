# CLAUDE.md

Guidance for Claude Code working in this repo.

## Project

FastAPI mock backend for a Travel Planner agent. Everything is faked except keyless Open-Meteo calls (`/weather`, `/air-quality`, `/destinations/{city}/climate`) and `/*/route` (OpenRouteService, haversine fallback).

Work in the **repo root** (`app/`, `tests/`, `scripts/`). Ignore `apps/` and `packages/` — stale, not buildable.

## Run & Test

```bash
# Setup
uv venv && source .venv/bin/activate && uv pip install -r requirements.txt

# Dev
make dev          # uvicorn + hot-reload, Swagger at /docs
make test         # 685 tests on SQLite (fast, zero-config)
make test-docker  # same tests on Postgres (cross-engine parity)
make seed         # re-seed reference data into DATABASE_URL

# Lint / format
ruff check app scripts
ruff format app scripts

# Debug: run a single test file
.venv/bin/pytest tests/api/trip/test_trip_budget.py -xvs

# Debug: open SQLite shell
sqlite3 travel.db

# Debug: check alembic migration state
.venv/bin/alembic current
.venv/bin/alembic upgrade head

# Debug: tail app logs
make dev 2>&1 | grep -v "200 OK"
```

## Layout

```
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
