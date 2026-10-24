# Monorepo root Makefile — delegates BE targets into apps/api, FE via pnpm/turbo.
# BE (apps/api) keeps its own Makefile; this is a thin convenience layer.
.PHONY: help install dev api-anthropic seed-anthropic test test-docker lint seed api fe web up down build diagram eval-smoke eval-full eval-html eval-baseline eval-compare eval-check research-smoke sim-up sim-down sim-reset sim-run

help:           ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

install:        ## Install JS deps (pnpm) — BE deps: see apps/api (uv)
	pnpm install

dev:            ## Run everything (turbo) — BE + FE dev servers
	pnpm turbo run dev

build:          ## Build all apps (turbo)
	pnpm turbo run build

lint:           ## Lint all apps (turbo)
	pnpm turbo run lint

test:           ## Run the BE suite (delegates to apps/api)
	$(MAKE) -C apps/api test

test-docker:    ## Run the BE suite on Postgres in Docker
	$(MAKE) -C apps/api test-docker

seed:           ## Seed the BE database
	$(MAKE) -C apps/api seed

api:            ## Run only the BE dev server
	$(MAKE) -C apps/api dev

api-anthropic:  ## Run only the BE dev server on Claude (sonnet-5-5 / haiku-5-5)
	$(MAKE) -C apps/api dev-anthropic

seed-anthropic: ## Set agent_config rows to the Claude 5.5 per-agent map
	$(MAKE) -C apps/api seed-anthropic

fe:             ## Run the FE dev server (cd apps/web → nvm use stable → pnpm run dev)
	. $${NVM_DIR:-$$HOME/.nvm}/nvm.sh && cd apps/web && nvm use stable && pnpm run dev

web: fe         ## Alias for `fe`

up:             ## Build + start api + Postgres in Docker (delegates to apps/api)
	$(MAKE) -C apps/api up

down:           ## Stop the Docker stack (delegates to apps/api)
	$(MAKE) -C apps/api down

diagram:        ## Render WORKFLOW_DIAGRAM.md → self-contained WORKFLOW_DIAGRAM.html
	node scripts/render-workflow-diagram.mjs

eval-smoke eval-full eval-html eval-baseline eval-compare eval-check:  ## Agent eval (delegates to apps/api; see apps/api/eval/README.md)
	$(MAKE) -C apps/api $@

research-smoke:  ## Keyed trip-research smoke (delegates to apps/api; pass ARGS='--dry-run')
	$(MAKE) -C apps/api research-smoke ARGS='$(ARGS)'

# Sim batch size defaults; override with `make sim-run N=... PARALLEL=...`.
N ?= 8
PARALLEL ?= 3

sim-up sim-down sim-reset:  ## Sim Compose stack (delegates to apps/api)
	$(MAKE) -C apps/api $@

sim-run:        ## Run the simulator (delegates to apps/api; e.g. make sim-run N=8 PARALLEL=3)
	$(MAKE) -C apps/api sim-run N=$(N) PARALLEL=$(PARALLEL) PERSONAS='$(PERSONAS)' SEED='$(SEED)'
