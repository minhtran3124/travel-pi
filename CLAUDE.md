# CLAUDE.md

Travel Planner monorepo (pnpm workspaces + Turborepo): FastAPI backend in `apps/api/`,
Next.js frontend in `apps/web/`.

## Models

Always use the Claude 5.5 family:

- **Opus** advises: planning, architecture, hard debugging.
- **Sonnet or Haiku** writes the code.
- **Haiku** searches, finds files and runs checks.

## Run

```bash
# Setup (once, from repo root)
uv venv && source .venv/bin/activate && uv pip install -r apps/api/requirements.txt
pnpm install

# From repo root
make dev          # BE + FE dev servers (turbo)
make api          # BE only — uvicorn + hot-reload, Swagger at /docs
make web          # FE only — Next.js dev server
make seed         # seed the BE database
make local        # db + redis + worker + api in Docker, live logs, Ctrl+C stops (migrates + seeds on start); make local-down cleans up
make prod         # simulate prod locally (Render topology: 2 web + nginx + worker) on :8080, live logs; make prod-down / prod-verify
```

## Test & Lint

```bash
make test         # BE suite on SQLite (fast, zero-config)
make test-docker  # same suite on Postgres in Docker
make lint         # lint all apps (turbo)
make eval-smoke   # agent eval, 20 cases, real agent, no judge (needs Docker db + apps/api/.env)
make eval-check   # judged full eval + regression gate vs eval/baselines/main.json (paid; see apps/api/eval/README.md)

# Single test file (from apps/api/)
../../.venv/bin/python -m pytest tests/api/trip/test_trip_budget.py -xvs

# Python lint/format (from apps/api/)
ruff check app scripts
ruff format app scripts
```

## Run and test

- **Test:** `make test` (BE suite on SQLite)
- **Targeted test** (from `apps/api/`): `../../.venv/bin/python -m pytest <path> -xvs`
- **Lint:** `make lint` (all apps); Python only, from `apps/api/`: `ruff check app scripts`
- **Full suite:** `make test` + `make lint`; add `make test-docker` to cover Postgres

## Environment

- **Python:** single venv at repo root (`.venv`); `apps/api/Makefile` uses `VENV ?= ../../.venv`.
- **Node:** use **v24** for any FE/pnpm work
  (`export PATH="$HOME/.nvm/versions/node/v24.22.2/bin:$PATH"`); pnpm 11 requires Node ≥22.13.
- **Database:** dev runs on Postgres in Docker (`make local`); SQLite is the config default and
  backs the fast unit-test suite (`make test`). Selected by `DATABASE_URL`. Schema versioned by
  Alembic (`../../.venv/bin/alembic current | upgrade head` from `apps/api/`).
- **LLM:** real provider when API keys are set; `FakeLLM` in tests (no network).
- **Shell:** zsh. Run BE commands from `apps/api/`, FE commands from `apps/web/`
  (or via the root `Makefile`).

## Git

- **PRs:** `main` is the integration branch — feature PRs target `main`. The git remote is named
  `github` (not `origin`), so `git fetch/push` use `github` and `gh` commands need `--repo minhtran3124/travel-pi`. Use the `minhtran3124` gh
  account (`gh auth switch --user minhtran3124`).

<!-- OPENWIKI:START -->

## OpenWiki

@AGENTS.md

<!-- OPENWIKI:END -->
