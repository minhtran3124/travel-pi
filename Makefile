.PHONY: help install dev up down logs exec-api exec-db migrate seed test test-docker fmt lint

help:           ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

install:        ## Create venv + install deps (local)
	uv venv && uv pip install -r requirements.txt

dev:            ## Run the app locally on SQLite (no Docker)
	.venv/bin/uvicorn app.main:app --reload --port 8000

up:             ## Build + start app + Postgres in Docker
	docker compose up

down:           ## Stop the Docker stack
	docker compose down

logs:           ## Tail Docker logs
	docker compose logs -f

exec-api:       ## Open a shell in the running api container
	docker compose exec api sh

exec-db:        ## Open psql in the running db container
	docker compose exec db psql -U travel travel

migrate:        ## Run Alembic migrations against the configured DATABASE_URL
	.venv/bin/alembic upgrade head

seed:           ## Seed the configured DATABASE_URL from app/data
	.venv/bin/python -c "from app.db.engine import get_session_factory; from app.core.config import get_settings; from app.db.seed import seed_all; seed_all(get_session_factory(get_settings().database_url))"

test:           ## Run the suite locally on SQLite
	.venv/bin/python -m pytest tests/ -q

test-docker:    ## Run the suite in Docker against isolated Postgres
	docker compose -f docker-compose.test.yml up --build \
	  --abort-on-container-exit --exit-code-from tests; \
	  docker compose -f docker-compose.test.yml down -v

fmt:            ## Format
	.venv/bin/ruff format app scripts

lint:           ## Lint
	.venv/bin/ruff check app scripts
