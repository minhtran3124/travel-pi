---
type: overview
title: Monorepo overview
description: The shape of the travel-pi repository — a pnpm and Turborepo workspace holding a Next.js web app and a FastAPI backend that also hosts the LangGraph travel agent, how the web app reaches the API through a proxy and a generated typed client, the backend's layering, the product boundary between real user data and synthetic inventory, the run and build entrypoints, and where the cross-cutting documents live.
tags: [monorepo, pnpm, turborepo, nextjs, fastapi, architecture, overview, entrypoints]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-74dac8f3a8700bf870db47a8
    resource: repo://apps/api/Makefile
  - id: openwiki-source-999f60ece775e48a66373ded
    resource: repo://apps/web/next.config.ts
  - id: openwiki-source-99de51df25f29bfc72caf823
    resource: repo://apps/web/package.json
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-5b54a58d1b51cd490b0e7162
    resource: repo://package.json
  - id: openwiki-source-40275cb92c3610938f16ade3
    resource: repo://pnpm-workspace.yaml
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-d0283cae65f2f97920e99cc2
    resource: repo://TECHSTACKS.md
  - id: openwiki-source-f9dd93415b71cf5360e877f1
    resource: repo://techstacks/architecture.md
  - id: openwiki-source-440ae1e215cb02721dda855c
    resource: repo://turbo.json
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Monorepo overview

`travel-pi` is a **pnpm workspace orchestrated by Turborepo** with two applications: `apps/web`, a Next.js App Router frontend in TypeScript, and `apps/api`, a FastAPI backend that owns the domain APIs and the LangGraph travel agent. The root `package.json` pins `pnpm@11.9.0` and Node ≥ 22.13; `pnpm-workspace.yaml` includes `apps/*` and `packages/*` (no shared packages exist yet). Python is managed separately with `uv` in a single `.venv` at the repository root, which `apps/api/Makefile` resolves as `../../.venv`.

## What the product is

An AI-assisted travel planner: plan a trip through conversation, discover places, check weather, search flights and hotels, book, track a budget and keep a journal. The product **deliberately mixes real persisted user data with safe synthetic inventory**: trips, bookings, expenses, saved places, journals, conversations and agent configuration are real CRUD rows, while flight results, hotel availability and FX rates are generated deterministically from seed data. Weather, air quality, climate normals and routing call real keyless or key-optional services, and the agent calls a real LLM provider only when keys are set; tests run entirely on a deterministic `FakeLLM`. There is no payment processing or external booking provider.

## How the two apps connect

```
apps/web (Next.js, TypeScript)
   │  /api/be/*  → rewritten by next.config.ts to NEXT_PUBLIC_API_URL
   ▼
apps/api (FastAPI)
   routers → services → repositories → SQLite / Postgres
   └─ LangGraph agent: supervisor → specialists → tools, streamed over SSE
```

- The web app's API client is `openapi-fetch` typed against `src/lib/api/schema.d.ts`, which `pnpm gen:api` regenerates from the running backend's `/openapi.json`. That is why the backend fails startup on duplicate operationIds. The client uses a relative `baseUrl` of `/api/be`, and `next.config.ts` rewrites `/api/be/:path*` to the backend origin (`NEXT_PUBLIC_API_URL`, default `http://localhost:8000`). A client middleware attaches the Supabase bearer token and mints idempotency keys for trip-creating POSTs. See [Web app shell, routing and auth](../frontend/app-shell-and-routing.md).
- The chat widget consumes the backend's typed Server-Sent Events; see [Chat widget and streaming client](../frontend/chat-and-streaming-client.md) and [Agent chat endpoints, SSE streaming and side panels](../agent/streaming-and-side-panels.md).
- Identity is Supabase on both sides: the browser holds the session, the API verifies the JWT against the project's JWKS. See [Authentication and user tiers](../concepts/auth-and-tiers.md).

## Backend layout

Inside `apps/api/app/`:

| Folder | Role |
|---|---|
| `main.py`, `core/` | App factory, settings, lifespan, middleware, errors, auth, rate limiting, dates and text helpers |
| `routers/` | One file per endpoint group; HTTP interface only |
| `services/` | Business logic; raise domain exceptions, never `HTTPException` |
| `repositories/` | The only place SQLAlchemy ORM models are touched |
| `db/`, `data/`, `alembic/` | Engine and session DI, ORM models, idempotent seeder; `data/` is the seed source of truth; migrations |
| `schemas/` | Pydantic v2 request and response models |
| `agents/`, `tools/`, `prompts/`, `memory/`, `streaming/`, `rag/`, `clients/` | The travel agent: graph, specialists, tool registry, versioned prompts, memory, SSE mapping, retrieval, LLM client |
| `mcp/` | A FastMCP server that exposes the tool registry to external clients |
| `templates/` | Jinja2 pages for the operator dashboard |

The layering rule is **routers → services → repositories** with no use-case layer, and agents, tools and MCP are thin adapters over services. Details and the enforcing tests are on [Backend request lifecycle](backend-request-lifecycle.md); the agent side starts at [Agent graph and supervisor routing](../agent/graph-and-supervisor.md). Beside the app package sit `eval/` and `evalkit/` (the agent evaluation harness, see [Agent evaluation harness](../testing/agent-eval-harness.md)), `tests/`, `scripts/`, and the Docker files.

## Frontend layout

`apps/web/src/` holds `app/` (App Router routes: home, auth, trips, bookings, flights, hotels, places, city guides), `components/` (app shell, chat, feature folders, shared UI, theme), `lib/` (typed API client and query keys, SSE parsing, Supabase clients, identity helpers), `i18n/` and `messages/` for `next-intl`, and colocated Vitest tests. Playwright end-to-end specs live in `apps/web/playwright/`. See the frontend pages under `frontend/`.

## Entrypoints and everyday commands

The root `Makefile` is a thin layer: `make dev` runs both dev servers through Turbo, `make api` and `make web` run one side, `make test` runs the backend suite on SQLite, `make test-docker` runs it on Postgres, `make up`/`make down` manage the Docker stack, `make seed` seeds the database, `make lint` lints both apps, and the `eval-*` targets delegate to the backend's evaluation harness. Turbo's pipeline (`turbo.json`) defines `build` (depends on upstream builds, caches `.next/` and `dist/`), `dev` (persistent, uncached), `lint` and `test`. Backend commands run from `apps/api/` and frontend commands from `apps/web/`. Full setup and toolchain notes are on [Local development, Docker and CI](../operations/local-dev-docker-and-ci.md).

## Where the cross-cutting documents live

- `README.md` (setup and product boundaries), `AGENTS.md` (orientation and mental model for agents and new contributors), `CLAUDE.md` (run, test and git conventions), `TECHSTACKS.md` (versions sourced from the manifests), `WORKFLOW.md` and `WORKFLOW_DIAGRAM.md` (the agent's request flow).
- `techstacks/` holds the architecture, guidelines, frontend and LangGraph profiles that reviews are measured against.
- `docs/decisions/` holds the architecture decision records; `docs/solutions/` is the compounded knowledge base of bugs, patterns and decisions; `specs/<slug>/` holds one folder per feature with its plan, summary and review, and is git-tracked as the feature history.
- `.claude/` is the engineering harness (rules, skills, hooks) and is not part of the runtime.
