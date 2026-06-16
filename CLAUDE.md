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
calls) **except** `/weather` (Open-Meteo) and `/*/route` (OpenRouteService).
Current endpoint list lives in `APIS.md`; `mock-api-spec.md` is the original
contract (now stale on layout).

## Run it

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000          # Swagger at /docs
.venv/bin/python -m pytest tests/ -v               # 336 tests
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
  crud/          # raw SQLite data access, no logic
  schemas/       # Pydantic v2 models (extend AppBaseModel)
  data/          # read-only seed data (airports, cities, hotels, places, tips, countries)
tests/           # pytest, isolated temp SQLite DB per run (conftest.py)
```

## Architecture rules

- **Layering:** routers → services (rules) → crud (SQL). Services raise domain
  exceptions (`NotFoundError`→404, `ConflictError`→409, `UpstreamError`→502) and
  never import `HTTPException`. `main.py` turns `AppError`, `HTTPException`, and
  `RequestValidationError` into one JSON envelope
  (`{error, message, status_code, path, [errors]}`). Routes declare codes via
  `responses=error_responses(...)`.
- **Bookings are the only mutable state** (SQLite `travel.db`); table created on
  startup in `core/lifespan.py`. `total_price` is always computed server-side —
  requests never carry a price. `GET /bookings/{id}` accepts the UUID or the
  derived `confirmation_code`; `cancel` is a soft, idempotent state change.
- **Deterministic generation, never stored:** flights and hotel availability are
  generated from an MD5 seed (flights: `origin-dest-date`; rooms:
  `hotel.id-check_in-check_out`), so the same query always returns the same
  result and IDs reverse back into search params. **Changing the seed algorithm
  breaks existing IDs.**
- **Async only for real network I/O:** `weather_service` and `routing_service`
  (and their `httpx.AsyncClient`) are async; everything else is sync. Routing
  degrades to an offline haversine estimate with no `ORS_API_KEY` (`source` field
  says which); results are cached in-process.
- **Seed data:** `data/countries.py` is the source of truth for countries; other
  data files validate against it at import (typos fail loudly on startup). Tips
  are positional-ID'd — **append only, never reorder**.
- Routes return typed `response_model`s so the FE can codegen TS types.

## Conventions

- Python 3.10+ hints (`list[X]`, `X | None`), Pydantic v2.
- `datetime.now(timezone.utc)`, never `utcnow()`.
- `logging.getLogger(__name__)`, never `print()`.
- **Fuzzy name resolution everywhere** free-text city/country is accepted, via
  `core/text.py` (`best_match` / `fuzzy_filter`). Resource IDs (UUIDs, IATA)
  stay exact. An unrecognised city/country returns `count: 0`, not 404.
- Keep it minimal — no auth, ORM, pagination, or rate limiting (see
  `mock-api-spec.md` §1). Console logging is in scope; anything heavier is not.
