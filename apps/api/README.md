# Travel Planner API

A travel-planning backend with full CRUD APIs — trips, bookings, expenses, hotels, places — persisted in SQLite/Postgres, plus a LangGraph AI agent. Flights and hotel availability are generated deterministically from seed data (no external booking providers, no payments); weather/air-quality/climate and routing call real keyless services.

## Run

### Local (SQLite)

Requires **Python 3.10+** and **[uv](https://docs.astral.sh/uv/)**:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
make install    # create venv + install deps
make dev        # start at http://localhost:8000
make test       # 2858 tests on SQLite
```

### Docker + Postgres

```bash
make up         # build + start api and db containers
make logs       # tail logs
make down       # stop
```

On startup: Postgres health check → `alembic upgrade head` → seed all reference data. Everything runs automatically.

Shell into a running container:

```bash
make exec-api   # sh in the api container
make exec-db    # psql in the db container
```

### Tests on isolated Postgres

```bash
make test-docker    # same suite against a throwaway Postgres DB
```

## Database

| Context | `DATABASE_URL` |
|---------|----------------|
| Local / tests | `sqlite:///travel.db` (default) |
| Docker | `postgresql+psycopg://travel:travel@db:5432/travel` |
| Docker tests | `postgresql+psycopg://test:test@test-db:5432/test` (ephemeral) |

**Migrations** run automatically in Docker via `docker/entrypoint.sh`. To run manually:

```bash
make migrate
```

**Seed data** (countries, airlines, airports, cities, hotels, places, tips, visa, FX) loads from `app/data/` on every startup — idempotent, never duplicates. To re-seed manually:

```bash
make seed                       # local
docker compose restart api      # Docker (re-seeds on restart)
```

## Use it

- **Swagger UI:** http://localhost:8000/docs
- **Flight board:** http://localhost:8000/dashboard/flights
- **Air quality:** http://localhost:8000/dashboard/air-quality
- **Agent runs:** http://localhost:8000/dashboard/agent-runs — per-turn token/cost/latency metrics (`cost_usd` is an estimate from `app/core/pricing.py`, verified 2026-09-03)
- **Full API reference:** [APIS.md](./APIS.md)

Generate TypeScript types:

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o ./types/api.ts
```

## Notes

- **Flights** are generated deterministically from `origin + destination + date` — same query always returns the same 5 flights and IDs.
- **Hotels** are a fixed list of 344 across 72 cities in 24 countries spanning Asia, Europe, Oceania, the Middle East and North America.
- **Bookings and trips** persist across restarts (SQLite locally, Postgres in Docker).
- **CORS** is fully open.
- `/docs` is disabled when `ENVIRONMENT=production`.

## Project layout

```
app/
├── main.py        # app factory, CORS, error handling
├── core/          # config, logging, lifespan
├── routers/       # one file per endpoint group
├── services/      # business logic
├── repositories/  # SQLAlchemy ORM data access
├── schemas/       # Pydantic v2 models
├── templates/     # Jinja2 HTML pages
└── data/          # seed source of truth
tests/             # pytest suite
scripts/           # data generators
```

Add seed hotels:

```bash
python scripts/generate_data.py hotels --city "Da Nang" --count 3
# prints records — copy into app/data/hotels.py
```
