# Monorepo root Makefile — delegates BE targets into apps/api, FE via pnpm/turbo.
# BE (apps/api) keeps its own Makefile; this is a thin convenience layer.
.PHONY: help install dev test test-docker lint seed api web build

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

web:            ## Run only the FE dev server
	pnpm --filter @travel/web dev
