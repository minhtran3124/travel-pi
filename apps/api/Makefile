# Backend Makefile. The monorepo root Makefile forwards every target here, so run
# `make <target>` from either directory.

# Single venv lives at the monorepo root (../../.venv). Override with `make VENV=.venv ...`.
VENV ?= ../../.venv
PY   := $(VENV)/bin/python

# $(call wait_http,URL,SECONDS): block until URL answers 2xx, fail after SECONDS.
wait_http = @echo "waiting for $(1) ..."; i=0; \
	until curl -fsS $(1) >/dev/null 2>&1; do \
	  i=$$((i+1)); [ $$i -ge $(2) ] && { echo "$(1) not healthy after $(2)s"; exit 1; }; sleep 1; \
	done; echo "up: $(1)"

.PHONY: help
help:           ## List targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

# --- Setup & dev server ------------------------------------------------------

.PHONY: install dev dev-anthropic seed-anthropic dev-token migrate seed
install:        ## Create venv + install deps (local)
	uv venv $(VENV) && uv pip install --python $(PY) -r requirements.txt

dev:            ## Run the app on the host (uvicorn --reload) against $DATABASE_URL from .env
	$(VENV)/bin/uvicorn app.main:app --reload --port 8000

dev-anthropic:  ## Run the app on Claude (sonnet-5-5 / haiku-5-5) via process env; .env untouched. Needs ANTHROPIC_API_KEY in .env
	LLM_PROVIDER=anthropic LLM_MODEL=claude-sonnet-5-5 FAST_LLM_MODEL=claude-haiku-5-5 $(MAKE) dev

seed-anthropic: ## Point agent_config rows at Claude (Haiku fast nodes, Sonnet specialists + research); idempotent
	$(PY) -m scripts.seed_agent_config --preset anthropic-local

dev-token:      ## Print a real Supabase access token for a dev user (needs SUPABASE_URL SUPABASE_ANON_KEY DEV_EMAIL DEV_PASSWORD in the shell)
	@test -n "$$SUPABASE_URL" -a -n "$$SUPABASE_ANON_KEY" -a -n "$$DEV_EMAIL" -a -n "$$DEV_PASSWORD" || { echo "Set SUPABASE_URL SUPABASE_ANON_KEY DEV_EMAIL DEV_PASSWORD (see README: Local auth token)" >&2; exit 1; }
	@curl -sf "$${SUPABASE_URL%/}/auth/v1/token?grant_type=password" -H "apikey: $$SUPABASE_ANON_KEY" -H "Content-Type: application/json" \
		-d "{\"email\":\"$$DEV_EMAIL\",\"password\":\"$$DEV_PASSWORD\"}" \
		| $(PY) -c "import json,sys; print(json.load(sys.stdin)['access_token'])"

migrate:        ## Run Alembic migrations against the configured DATABASE_URL
	$(VENV)/bin/alembic upgrade head

seed:           ## Seed the configured DATABASE_URL from app/data (the API also seeds on startup)
	$(PY) -c "from app.db.engine import get_session_factory; from app.core.config import get_settings; from app.db.seed import seed_all; seed_all(get_session_factory(get_settings().database_url))"

# --- Local stack: db + redis + worker + api (docker-compose.yml) -------------

COMPOSE = docker compose

.PHONY: local local-down local-reset local-logs exec-api exec-db
local:          ## Start db + redis + worker + api in Docker with live logs (Ctrl+C stops); migrates + seeds on start
	@echo "api http://localhost:8000 (docs /docs, dashboard /dashboard) | db :5433 | redis :6379 | FE: make web in another terminal"
	$(COMPOSE) up --build

local-down:     ## Remove the local stack's containers (keeps the db volume)
	$(COMPOSE) down

local-reset:    ## Remove the local stack's containers and drop the db volume
	$(COMPOSE) down -v

local-logs:     ## Follow the logs of an already-running local stack
	$(COMPOSE) logs -f --tail 100

exec-api:       ## Open a shell in the running api container
	$(COMPOSE) exec api sh

exec-db:        ## Open psql in the running db container
	$(COMPOSE) exec db psql -U travel travel

# --- Prod simulation: the Render topology (docker-compose.prodsim.yml) --------
# Postgres + Redis + one migrate job + 2 web instances behind an nginx proxy + 1 Arq worker.

PROD = docker compose -f docker-compose.prodsim.yml

# Value of KEY from apps/api/.env (empty when absent), so `make prod` needs no exported variables.
dotenv = $$(sed -n 's/^$(1)=//p' .env 2>/dev/null | tail -1 | tr -d '"')

# Supabase URL and Claude key come from .env (or PRODSIM_* in the shell); provider follows the key.
prod_env = k="$${PRODSIM_ANTHROPIC_API_KEY:-$(call dotenv,ANTHROPIC_API_KEY)}"; \
	export PRODSIM_ANTHROPIC_API_KEY="$$k" \
	       PRODSIM_SUPABASE_URL="$${PRODSIM_SUPABASE_URL:-$(call dotenv,SUPABASE_URL)}" \
	       PRODSIM_LLM_PROVIDER="$${PRODSIM_LLM_PROVIDER:-$$([ -n "$$k" ] && echo anthropic || echo openai)}";

.PHONY: prod prod-down prod-logs prod-verify prod-chaos
prod:           ## Simulate production locally with live logs (Ctrl+C stops): migrate job + 2 web + nginx + worker on http://localhost:8080 (Supabase URL + Claude key read from .env)
	@echo "prod sim http://localhost:8080 | FE: make web-prod | break it: make prod-chaos | clean up: make prod-down (other terminal)"
	$(prod_env) $(PROD) up --build lb worker

prod-down:      ## Remove the prod simulation's containers and drop its volume
	$(PROD) down -v

prod-logs:      ## Follow the logs of an already-running prod simulation
	$(PROD) logs -f --tail 100

prod-verify:    ## Rehearse the Render topology: build, start, verify, tear down (no key, no spend)
	# Not `up --abort-on-container-exit`: the one-shot migrate job exits 0 and would stop the whole stack.
	( $(PROD) up -d --build --wait lb worker && $(PROD) run --rm --no-deps verify ); rc=$$?; \
	[ $$rc -eq 0 ] || $(PROD) logs --no-color --tail 80 api-1 api-2 worker; \
	echo "--- migrations ran in: $$($(PROD) logs migrate api-1 api-2 worker 2>/dev/null | grep -c 'Running migrations') container(s) (expect 1)"; \
	echo "--- web container memory (api-1, api-2)"; \
	ids="$$($(PROD) ps -q api-1 api-2)"; \
	[ -z "$$ids" ] || docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' $$ids; \
	$(PROD) down -v; exit $$rc

prod-chaos:     ## Break the running prod simulation (stop a web, kill the worker, stop redis) and check recovery
	sh scripts/prodsim_chaos.sh

# --- Sim stack: persona simulator (docker-compose.sim.yml) -------------------

SIM = docker compose -f docker-compose.sim.yml

# Sim batch size defaults; override with `make sim-run N=... PARALLEL=...`.
N ?= 8
PARALLEL ?= 3

.PHONY: sim-up sim-down sim-reset sim-run
sim-up:         ## Build + start the sim stack (api-sim :8001 + db-sim), wait for /healthz
	$(SIM) up -d --build
	$(call wait_http,http://localhost:8001/healthz,90)

sim-down:       ## Stop the sim stack (keeps the volume)
	$(SIM) down

sim-reset:      ## Stop the sim stack and remove its volume
	$(SIM) down -v

sim-run:        ## Run the simulator: make sim-run N=8 PARALLEL=3 [PERSONAS=file] [SEED=n]
	$(PY) -m sim --n $(N) --parallel $(PARALLEL) \
	  $(if $(PERSONAS),--personas $(PERSONAS),) $(if $(SEED),--seed $(SEED),)

# --- Tests & lint ------------------------------------------------------------

.PHONY: test test-docker fmt lint
test:           ## Run the suite locally on SQLite
	$(PY) -m pytest tests/ -q -n auto

test-docker:    ## Run the suite in Docker against isolated Postgres
	docker compose -f docker-compose.test.yml up --build \
	  --abort-on-container-exit --exit-code-from tests; \
	  docker compose -f docker-compose.test.yml down -v

fmt:            ## Format
	$(VENV)/bin/ruff format app scripts

lint:           ## Lint
	$(VENV)/bin/ruff check app scripts

# --- Agent eval --------------------------------------------------------------

# Committed baseline report used by eval-compare, picked by provider (PROVIDER=anthropic or LLM_PROVIDER=anthropic -> main-anthropic.json).
# Override with `make BASELINE=... eval-compare`.
EVAL_PROVIDER := $(or $(PROVIDER),$(LLM_PROVIDER))
BASELINE ?= eval/baselines/main$(if $(filter anthropic,$(EVAL_PROVIDER)),-anthropic).json
EVAL_OUT   = --out eval/reports/latest.json --html eval/reports/latest.html
EVAL_FLAGS = $(if $(PROVIDER),--provider $(PROVIDER)) $(if $(JUDGE),--judge-provider $(JUDGE))

.PHONY: eval-smoke eval-full eval-html eval-baseline eval-compare eval-check loadtest research-smoke
eval-smoke:     ## Keyless agent eval: deterministic + trajectory checks only (PROVIDER=anthropic runs the agent on Claude)
	$(PY) -m eval --suite smoke $(EVAL_FLAGS) $(EVAL_OUT)
	$(PY) scripts/loadtest_chat.py --concurrency 5 --turns 1

eval-full:      ## Judged agent eval (PROVIDER=anthropic runs the agent on Claude; JUDGE=anthropic runs the judge on Claude): full matrix, k=3 repeats, writes a Report JSON + HTML
	$(PY) -m eval --suite full --repeat 3 $(EVAL_FLAGS) $(EVAL_OUT)

eval-html:      ## Re-render an existing report JSON as a browsable HTML page
	$(PY) -m evalkit.report_html eval/reports/latest.json eval/reports/latest.html

eval-baseline:  ## Save the latest report as the committed baseline
	mkdir -p eval/baselines && cp eval/reports/latest.json $(BASELINE)

eval-compare:   ## Compare the latest report against the committed baseline (exit 1 on regression)
	test -f $(BASELINE) || { echo "no baseline at $(BASELINE) — run 'make eval-baseline' after a trusted 'make eval-full'"; exit 1; }
	$(PY) -c "from evalkit.baseline import compare, render_table; from evalkit.report import load_report; import sys; report = load_report('eval/reports/latest.json'); baseline = load_report('$(BASELINE)'); diff = compare(report, baseline); print(render_table(diff)); sys.exit(diff.exit_code())"

eval-check: eval-full eval-compare  ## Local regression gate (E002: judged eval never runs on CI) — full judged run, then compare

loadtest:       ## Concurrent-chat load test on FakeLLM: make loadtest ARGS='--concurrency 5 10 20 --processes 4 --database-url postgresql+psycopg://...' (exit 1 if a <=10 level fails)
	$(PY) scripts/loadtest_chat.py $(ARGS)

research-smoke:  ## Keyed trip-research smoke (NOT in CI): pass ARGS='--dry-run' for the keyless path, ARGS='--provider anthropic' for Claude
	$(PY) -m eval.research_smoke $(ARGS)

# --- Legacy names (kept so docs, muscle memory and old links keep working) ----

.PHONY: up down logs prodsim prodsim-up prodsim-chaos prodsim-down
up: local
down: local-down
logs: local-logs
prodsim: prod-verify
prodsim-up: prod
prodsim-chaos: prod-chaos
prodsim-down: prod-down
