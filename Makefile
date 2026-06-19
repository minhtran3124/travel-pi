.PHONY: help install dev up down logs migrate test test-docker fmt lint

help:           ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

install:        ## Create venv + install deps (local)
	uv venv && uv pip install -r requirements.txt

dev:            ## Run the app locally on SQLite (no Docker)
	.venv/bin/uvicorn app.main:app --reload --port 8000

up:             ## Build + start app + Postgres in Docker
	docker compose up --build -d

down:           ## Stop the Docker stack
	docker compose down

logs:           ## Tail Docker logs
	docker compose logs -f

migrate:        ## Run Alembic migrations against the configured DATABASE_URL
	.venv/bin/alembic upgrade head

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
