# Monorepo root Makefile — a thin layer. BE targets live in apps/api/Makefile and are forwarded
# by one rule below; FE runs through pnpm/turbo. Command-line variables (N=, ARGS=, PROVIDER=, ...)
# reach the BE Makefile on their own.

# Node 24 for any FE/pnpm work (pnpm 11 needs Node >= 22.13).
NODE24 = . $${NVM_DIR:-$$HOME/.nvm}/nvm.sh && nvm use 24 && corepack enable pnpm

# Targets defined in apps/api/Makefile; see `make help` for what each one does.
API_TARGETS := \
  local local-down local-reset local-logs up down logs \
  prod prod-down prod-logs prod-verify prod-chaos prodsim prodsim-up prodsim-chaos prodsim-down \
  sim-up sim-down sim-reset sim-run \
  test test-docker seed migrate seed-anthropic \
  eval-smoke eval-full eval-html eval-baseline eval-compare eval-check research-smoke

.PHONY: help install dev build lint api api-anthropic fe web web-prod web-prodsim diagram $(API_TARGETS)

help:           ## List targets
	@echo "Root:"
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## .*$$' Makefile | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'
	@echo "Backend (apps/api/Makefile; run from the root when forwarded, else make -C apps/api <target>):"
	@$(MAKE) --no-print-directory -C apps/api help

install:        ## Install JS deps (pnpm) — BE deps: make -C apps/api install (uv)
	pnpm install

dev:            ## Run everything on the host (turbo) — BE + FE dev servers; needs a database (make local, or SQLite via .env)
	$(NODE24) && pnpm turbo run dev

build:          ## Build all apps (turbo)
	pnpm turbo run build

lint:           ## Lint all apps (turbo)
	pnpm turbo run lint

api:            ## Run only the BE dev server on the host (uvicorn --reload)
	$(MAKE) --no-print-directory -C apps/api dev

api-anthropic:  ## Run only the BE dev server on Claude (sonnet-5-5 / haiku-5-5)
	$(MAKE) --no-print-directory -C apps/api dev-anthropic

fe:             ## Run the FE dev server (nvm use 24 → pnpm run dev) against the local API
	$(NODE24) && cd apps/web && pnpm run dev

web: fe         ## Alias for `fe`

web-prod:       ## FE dev server against the prod simulation (make prod → http://localhost:8080)
	$(NODE24) && cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8080 pnpm run dev

web-prodsim: web-prod  ## Legacy name for web-prod

diagram:        ## Render WORKFLOW_DIAGRAM.md → self-contained WORKFLOW_DIAGRAM.html
	node scripts/render-workflow-diagram.mjs

$(API_TARGETS):
	@$(MAKE) --no-print-directory -C apps/api $@
