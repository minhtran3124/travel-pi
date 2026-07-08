# Monorepo root Makefile — delegates BE targets into apps/api, FE via pnpm/turbo.
# BE (apps/api) keeps its own Makefile; this is a thin convenience layer.
.PHONY: help install dev test test-docker lint seed api web up down build diagram

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

web:            ## Run the FE dev server on the Node pinned in apps/web/.nvmrc (24.17.0)
	. $${NVM_DIR:-$$HOME/.nvm}/nvm.sh && cd apps/web && nvm use && pnpm run dev

up:             ## Build + start api + Postgres in Docker (delegates to apps/api)
	$(MAKE) -C apps/api up

down:           ## Stop the Docker stack (delegates to apps/api)
	$(MAKE) -C apps/api down

diagram:        ## Render WORKFLOW_DIAGRAM.md → self-contained WORKFLOW_DIAGRAM.html
	node scripts/render-workflow-diagram.mjs
