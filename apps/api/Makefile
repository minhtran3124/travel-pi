.PHONY: help install dev up down logs exec-api exec-db migrate seed test test-docker fmt lint \
        eval-smoke eval-full eval-baseline eval-compare

# Single venv lives at the monorepo root (../../.venv). Override with `make VENV=.venv ...`.
VENV ?= ../../.venv

help:           ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

install:        ## Create venv + install deps (local)
	uv venv $(VENV) && uv pip install --python $(VENV)/bin/python -r requirements.txt

dev:            ## Run the app locally (uvicorn --reload) against $DATABASE_URL from .env
	$(VENV)/bin/uvicorn app.main:app --reload --port 8000

up:             ## Build + start app + Postgres in Docker
	docker compose up --build

down:           ## Stop the Docker stack
	docker compose down

logs:           ## Tail Docker logs
	docker compose logs -f

exec-api:       ## Open a shell in the running api container
	docker compose exec api sh

exec-db:        ## Open psql in the running db container
	docker compose exec db psql -U travel travel

migrate:        ## Run Alembic migrations against the configured DATABASE_URL
	$(VENV)/bin/alembic upgrade head

seed:           ## Seed the configured DATABASE_URL from app/data
	$(VENV)/bin/python -c "from app.db.engine import get_session_factory; from app.core.config import get_settings; from app.db.seed import seed_all; seed_all(get_session_factory(get_settings().database_url))"

test:           ## Run the suite locally on SQLite
	$(VENV)/bin/python -m pytest tests/ -q

test-docker:    ## Run the suite in Docker against isolated Postgres
	docker compose -f docker-compose.test.yml up --build \
	  --abort-on-container-exit --exit-code-from tests; \
	  docker compose -f docker-compose.test.yml down -v

fmt:            ## Format
	$(VENV)/bin/ruff format app scripts

lint:           ## Lint
	$(VENV)/bin/ruff check app scripts

eval-smoke:     ## Keyless agent eval: deterministic + trajectory checks only
	$(VENV)/bin/python -m eval --suite smoke

eval-full:      ## Judged agent eval: full matrix, k=3 repeats, writes a Report JSON
	$(VENV)/bin/python -m eval --suite full --repeat 3 --out eval/reports/latest.json

eval-baseline:  ## Save the latest report as the committed baseline
	mkdir -p eval/baselines && cp eval/reports/latest.json eval/baselines/main.json

eval-compare:   ## Compare the latest report against the committed baseline (exit 1 on regression)
	$(VENV)/bin/python -c "from evalkit.baseline import compare, render_table; from evalkit.report import load_report; import sys; report = load_report('eval/reports/latest.json'); baseline = load_report('eval/baselines/main.json'); diff = compare(report, baseline); print(render_table(diff)); sys.exit(diff.exit_code())"
