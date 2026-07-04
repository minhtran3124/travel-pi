# CLAUDE.md

Guidance for Claude Code working in this repo.

## Project

FastAPI mock backend for a Travel Planner agent. Everything is faked except keyless Open-Meteo calls (`/weather`, `/air-quality`, `/destinations/{city}/climate`), `/*/route` (OpenRouteService, haversine fallback), and the AI agent's LLM calls (real provider via `init_chat_model()` when keys are set; `FakeLLM` in tests). Flights, hotel availability, trips, bookings, and FX remain deterministic/DB-seeded fakes.

**Monorepo** (pnpm workspaces + Turborepo). The BE lives in `apps/api/` (FastAPI) and the
Next.js FE in `apps/web/`. Do BE work in `apps/api/`; the single Python venv stays at the
repo root (`.venv`), referenced by `apps/api/Makefile` via `VENV ?= ../../.venv`. A root
`Makefile` delegates to both apps: `make api | web | dev | test | lint | seed`.

New here? Start with `AGENTS.md` (orientation), then `TECHSTACKS.md` (stack) and
`WORKFLOW.md` (the AI agent architecture).

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
  agents/        # LangGraph supervisor + 5 ReAct sub-agents, nodes, state, checkpointer
  tools/         # agent tools grouped by domain (registry.py); also exposed via mcp/
  clients/llm.py # provider-agnostic LLM client (init_chat_model; FakeLLM in tests)
  memory/        # conversation memory (summarizer/store)
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
- **AI agent (`specs/travel-agent/`):** LangGraph graph (supervisor → planner/concierge/journal/booking/budget → reflection), built once in `core/lifespan.py`, served at `/agent/*`. Provider-agnostic via `init_chat_model()`; tests run on `FakeLLM` (no network). Full detail in `WORKFLOW.md`.

## Conventions

- Python 3.10+ hints, Pydantic v2. `datetime.now(timezone.utc)`, never `utcnow()`.
- Fuzzy name resolution for free-text city/country (`core/text.py`). Unknown city → `count: 0`, not 404.
- `logging.getLogger(__name__)`, never `print()`.
- No auth, pagination, or rate limiting.

## Design (dashboard only)

Before touching `/dashboard/*` templates: read `PRODUCT.md` + `DESIGN.md`. Tokens live in `app/templates/base.html` `:root`. Use `/impeccable` for design tasks.

## Knowledge Base
Solved problems, patterns, and architectural decisions: `docs/solutions/`
Browse the index: `docs/solutions/INDEX.md`
Critical learnings (read at planning time): `docs/solutions/critical-patterns.md`

## Shell & Git

- **Stage and commit as SEPARATE commands.** A PreToolUse hook blocks compound
  `git add … && git commit …` (the whole command is denied before the `add` runs).
  Run `git add <paths>` first, then `git commit …` as its own command.
- **Working directory after the monorepo move:** run BE commands from `apps/api/`
  (or via the delegating root `Makefile`), FE commands from `apps/web/`. New
  root-level docs belong at the repo root, not under `apps/`.
- **Node:** use **v24** for any FE/pnpm work
  (`export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`) — the `nvm`
  default is still 18, and pnpm 11 requires Node ≥22.13. See
  `docs/solutions/ci/pnpm-node-floor-mismatch.md`.
- **Shell is zsh:** use literal file lists and quote variables in `git mv`/loops
  (zsh word-splits; bash associative-array syntax breaks).
- **Before opening a PR:** confirm head branch, base branch (feature PRs target the
  latest integration branch, not `main`), and the active `gh` account
  (`minhtran3124` for this repo).
