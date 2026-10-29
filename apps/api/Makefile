.PHONY: help install dev dev-anthropic seed-anthropic dev-token up down logs exec-api exec-db migrate seed test test-docker fmt lint \
        eval-smoke loadtest eval-full eval-baseline eval-compare eval-check eval-html research-smoke \
        sim-up sim-down sim-reset sim-run prodsim prodsim-up prodsim-chaos prodsim-down

# Single venv lives at the monorepo root (../../.venv). Override with `make VENV=.venv ...`.
VENV ?= ../../.venv

# Committed baseline report used by eval-compare, picked by provider (PROVIDER=anthropic or LLM_PROVIDER=anthropic -> main-anthropic.json).
# Override with `make BASELINE=... eval-compare`.
EVAL_PROVIDER := $(or $(PROVIDER),$(LLM_PROVIDER))
BASELINE ?= eval/baselines/main$(if $(filter anthropic,$(EVAL_PROVIDER)),-anthropic).json

help:           ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

install:        ## Create venv + install deps (local)
	uv venv $(VENV) && uv pip install --python $(VENV)/bin/python -r requirements.txt

dev-anthropic:  ## Run the app on Claude (sonnet-5-5 / haiku-5-5) via process env; .env untouched. Needs ANTHROPIC_API_KEY in .env
	LLM_PROVIDER=anthropic LLM_MODEL=claude-sonnet-5-5 FAST_LLM_MODEL=claude-haiku-5-5 $(VENV)/bin/uvicorn app.main:app --reload --port 8000

seed-anthropic: ## Point agent_config rows at Claude (Haiku fast nodes, Sonnet specialists + research); idempotent
	$(VENV)/bin/python -m scripts.seed_agent_config --preset anthropic-local

dev-token:      ## Print a real Supabase access token for a dev user (needs SUPABASE_URL SUPABASE_ANON_KEY DEV_EMAIL DEV_PASSWORD in the shell)
	@test -n "$$SUPABASE_URL" -a -n "$$SUPABASE_ANON_KEY" -a -n "$$DEV_EMAIL" -a -n "$$DEV_PASSWORD" || { echo "Set SUPABASE_URL SUPABASE_ANON_KEY DEV_EMAIL DEV_PASSWORD (see README: Local auth token)" >&2; exit 1; }
	@curl -sf "$${SUPABASE_URL%/}/auth/v1/token?grant_type=password" -H "apikey: $$SUPABASE_ANON_KEY" -H "Content-Type: application/json" \
		-d "{\"email\":\"$$DEV_EMAIL\",\"password\":\"$$DEV_PASSWORD\"}" \
		| $(VENV)/bin/python -c "import json,sys; print(json.load(sys.stdin)['access_token'])"

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

eval-smoke:     ## Keyless agent eval: deterministic + trajectory checks only (PROVIDER=anthropic runs the agent on Claude)
	$(VENV)/bin/python -m eval --suite smoke $(if $(PROVIDER),--provider $(PROVIDER)) $(if $(JUDGE),--judge-provider $(JUDGE)) --out eval/reports/latest.json --html eval/reports/latest.html
	$(VENV)/bin/python scripts/loadtest_chat.py --concurrency 5 --turns 1

loadtest:       ## Concurrent-chat load test on FakeLLM: make loadtest ARGS='--concurrency 5 10 20 --processes 4 --database-url postgresql+psycopg://...' (exit 1 if a <=10 level fails)
	$(VENV)/bin/python scripts/loadtest_chat.py $(ARGS)

eval-full:      ## Judged agent eval (PROVIDER=anthropic runs the agent on Claude; JUDGE=anthropic runs the judge on Claude): full matrix, k=3 repeats, writes a Report JSON + HTML
	$(VENV)/bin/python -m eval --suite full --repeat 3 $(if $(PROVIDER),--provider $(PROVIDER)) $(if $(JUDGE),--judge-provider $(JUDGE)) --out eval/reports/latest.json --html eval/reports/latest.html

eval-html:      ## Re-render an existing report JSON as a browsable HTML page
	$(VENV)/bin/python -m evalkit.report_html eval/reports/latest.json eval/reports/latest.html

eval-baseline:  ## Save the latest report as the committed baseline
	mkdir -p eval/baselines && cp eval/reports/latest.json $(BASELINE)

eval-compare:   ## Compare the latest report against the committed baseline (exit 1 on regression)
	test -f $(BASELINE) || { echo "no baseline at $(BASELINE) — run 'make eval-baseline' after a trusted 'make eval-full'"; exit 1; }
	$(VENV)/bin/python -c "from evalkit.baseline import compare, render_table; from evalkit.report import load_report; import sys; report = load_report('eval/reports/latest.json'); baseline = load_report('$(BASELINE)'); diff = compare(report, baseline); print(render_table(diff)); sys.exit(diff.exit_code())"

eval-check: eval-full eval-compare  ## Local regression gate (E002: judged eval never runs on CI) — full judged run, then compare

research-smoke:  ## Keyed trip-research smoke (NOT in CI): pass ARGS='--dry-run' for the keyless path, ARGS='--provider anthropic' for Claude
	$(VENV)/bin/python -m eval.research_smoke $(ARGS)

# Sim batch size defaults; override with `make sim-run N=... PARALLEL=...`.
N ?= 8
PARALLEL ?= 3

sim-up:         ## Build + start the sim stack (api-sim :8001 + db-sim), wait for /healthz
	docker compose -f docker-compose.sim.yml up -d --build
	@echo "waiting for http://localhost:8001/healthz ..."
	@for i in $$(seq 1 90); do \
	  curl -fsS http://localhost:8001/healthz >/dev/null 2>&1 && { echo "api-sim up"; exit 0; }; \
	  sleep 1; \
	done; \
	echo "api-sim did not become healthy within 90s"; exit 1

sim-down:       ## Stop the sim stack (keeps the volume)
	docker compose -f docker-compose.sim.yml down

sim-reset:      ## Stop the sim stack and remove its volume
	docker compose -f docker-compose.sim.yml down -v

sim-run:        ## Run the simulator: make sim-run N=8 PARALLEL=3 [PERSONAS=file] [SEED=n]
	$(VENV)/bin/python -m sim --n $(N) --parallel $(PARALLEL) \
	  $(if $(PERSONAS),--personas $(PERSONAS),) $(if $(SEED),--seed $(SEED),)

PRODSIM = docker compose -f docker-compose.prodsim.yml

prodsim:        ## Rehearse the Render topology locally: build, start, verify, tear down (no key, no spend)
	# Not `up --abort-on-container-exit`: the one-shot migrate job exits 0 and would stop the whole stack.
	( $(PRODSIM) up -d --build --wait lb worker && $(PRODSIM) run --rm --no-deps verify ); rc=$$?; \
	[ $$rc -eq 0 ] || $(PRODSIM) logs --no-color --tail 80 api-1 api-2 worker; \
	echo "--- migrations ran in: $$($(PRODSIM) logs migrate api-1 api-2 worker 2>/dev/null | grep -c 'Running migrations') container(s) (expect 1)"; \
	$(PRODSIM) down -v; exit $$rc

# Value of KEY from apps/api/.env (empty when absent), so prodsim-up needs no exported variables.
dotenv = $$(sed -n 's/^$(1)=//p' .env 2>/dev/null | tail -1 | tr -d '"')

prodsim-up:     ## Run the prodsim stack in the foreground with live logs on http://localhost:8080 (Ctrl+C stops it; Supabase URL and Claude key read from .env)
	k="$${PRODSIM_ANTHROPIC_API_KEY:-$(call dotenv,ANTHROPIC_API_KEY)}"; \
	PRODSIM_SUPABASE_URL="$${PRODSIM_SUPABASE_URL:-$(call dotenv,SUPABASE_URL)}" \
	PRODSIM_ANTHROPIC_API_KEY="$$k" \
	PRODSIM_LLM_PROVIDER="$${PRODSIM_LLM_PROVIDER:-$$([ -n "$$k" ] && echo anthropic || echo openai)}" \
	$(PRODSIM) up --build lb worker

prodsim-chaos:  ## Break the running prodsim stack (stop a web, kill the worker, stop redis) and check recovery
	sh scripts/prodsim_chaos.sh

prodsim-down:   ## Stop the prodsim stack and drop its volume
	$(PRODSIM) down -v
