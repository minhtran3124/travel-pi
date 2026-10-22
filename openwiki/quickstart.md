---
type: guide
title: Quickstart
description: The entry page for the travel-pi wiki — what the product and repository are, the commands to run, test and lint both apps, the invariants that most often trip newcomers, and a task-routing map from the kind of work you are doing to the wiki page that explains that part of the system.
tags: [quickstart, onboarding, routing, commands, overview]
sources:
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-a2371d6362e5db4bc834ad03
    resource: repo://CLAUDE.md
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
---

# Quickstart

**travel-pi** is an AI-assisted travel planner: a Next.js web app (`apps/web`) over a FastAPI backend (`apps/api`) that owns the domain APIs and hosts a LangGraph multi-agent assistant. User data (trips, bookings, expenses, saved places, conversations) is real and persisted; travel inventory (flights, hotel availability, FX) is synthetic and deterministic; weather, air quality, climate and routing call real external services; the assistant calls a real LLM only when keys are set and a deterministic `FakeLLM` in tests. Start with [Monorepo overview](architecture/monorepo-overview.md) for the shape and [Agent graph and supervisor routing](agent/graph-and-supervisor.md) for the interesting part.

## Run it

```bash
corepack enable pnpm && pnpm install                          # Node 24, pnpm 11
uv venv && uv pip install --python .venv/bin/python -r apps/api/requirements.txt
cp apps/api/.env.example apps/api/.env && cp apps/web/.env.example apps/web/.env.local
make api      # FastAPI on :8000 (Swagger at /docs)
make web      # Next.js on :3000, proxies /api/be/* to :8000
make up       # or: API + pgvector Postgres in Docker (durable agent memory)
```

The API needs no `.env` and no LLM key to run on SQLite; the web app needs its public Supabase variables even locally. Details: [Local development, Docker and CI](operations/local-dev-docker-and-ci.md) and [Configuration and environments](architecture/configuration-and-environments.md).

## Test it

| Command | What |
|---|---|
| `make test` | backend pytest on a temp SQLite file, offline |
| `make test-docker` | the same suite on a throwaway Postgres (cross-engine parity) |
| `pnpm --filter @travel/web test` | Vitest unit and component tests |
| `pnpm e2e` (from `apps/web`) | Playwright, opt-in, needs the API on :8000 and e2e credentials |
| `make eval-smoke` / `make eval-check` | agent quality; the judged run is paid and never runs on CI |
| `make research-smoke` | keyed trip-research smoke (paid, never on CI); `ARGS='--dry-run'` is keyless |
| `make lint` | ruff for the backend, eslint for the web |

See [Backend test strategy](testing/backend-test-strategy.md), [Frontend unit tests and Playwright e2e](testing/frontend-tests-and-e2e.md) and [Agent evaluation harness](testing/agent-eval-harness.md).

## Things that surprise newcomers

- Editing a prompt file does nothing unless `active.yaml` points at that version. [Prompt registry](agent/prompt-registry.md)
- Without the dev Postgres, agent conversation history and long-term memory are in-memory and vanish on restart; a misbehaving thread is usually a poisoned checkpoint, so start a new conversation. [Conversation memory and persistence](agent/memory-and-persistence.md)
- Per-agent models live in the `agent_config` table and reach the running graph through a poll-refreshed cache and rebuild, not through env or a restart. [LLM providers and per-agent configuration](agent/llm-providers-and-agent-config.md)
- The planner searches but never books; booking is premium-only and runs behind a human-approval interrupt. [Guardrails](agent/guardrails-pii-and-hitl.md)
- Deep trip research is a **second graph** (deepagents), not a specialist. The chat's `research` node only books a background run, and progress streams from its own SSE route and in-process bus. Set `RESEARCH_ENABLED` and `NEXT_PUBLIC_RESEARCH_ENABLED` together. [Trip-research deep agent](agent/trip-research-deep-agent.md)
- Live web search is off unless `WEB_SEARCH_ENABLED` is on **and** a provider key is set, and the tools are never exposed over MCP. [Live web search](integrations/live-web-search.md)
- Tools with injected arguments must declare them in their `args_schema` or they are never injected. [Specialist sub-agents and the tool registry](agent/specialists-and-tools.md)
- List reads of reference data must `ORDER BY position`; an unordered `SELECT` silently drifts on Postgres. [Data layer and migrations](architecture/data-layer-and-migrations.md)
- A duplicate FastAPI handler name fails startup because it breaks the frontend's generated client; regenerate `schema.d.ts` with `pnpm gen:api` after contract changes. [Backend request lifecycle](architecture/backend-request-lifecycle.md)
- A real key or Postgres URL in `apps/api/.env` can redden the test suite; fixtures blank them explicitly. [Backend test strategy](testing/backend-test-strategy.md)

## Where to go, by task

| If you are… | Read |
|---|---|
| Adding or changing a REST endpoint | [Backend request lifecycle](architecture/backend-request-lifecycle.md), then the domain page: [Trips, itinerary and budget](domain/trips-itinerary-and-budget.md), [Bookings, flights and hotels](domain/bookings-flights-and-hotels.md), [Destinations, places and travel information](domain/destinations-places-and-travel-info.md) |
| Changing models, tables or migrations | [Data layer and migrations](architecture/data-layer-and-migrations.md) |
| Adding a setting or deploying | [Configuration and environments](architecture/configuration-and-environments.md), [Local development, Docker and CI](operations/local-dev-docker-and-ci.md) |
| Working on auth, ownership or tiers | [Authentication and user tiers](concepts/auth-and-tiers.md), [Rate limiting and quotas](concepts/rate-limiting-and-quotas.md) |
| Changing how the agent routes or reflects | [Agent graph and supervisor routing](agent/graph-and-supervisor.md), [Agent state, runtime context and reply language](agent/state-context-and-language.md) |
| Adding or fixing an agent tool or specialist | [Specialist sub-agents and the tool registry](agent/specialists-and-tools.md), [MCP server exposure](integrations/mcp-server.md), [Live web search](integrations/live-web-search.md) |
| Working on deep trip research | [Trip-research deep agent](agent/trip-research-deep-agent.md) (backend) and [Trip research UI](frontend/trip-research-ui.md) (Research tab, chat plan panel) |
| Editing a prompt | [Prompt registry](agent/prompt-registry.md), then verify with [Agent evaluation harness](testing/agent-eval-harness.md) |
| Touching memory, the checkpointer or RAG | [Conversation memory and persistence](agent/memory-and-persistence.md), [Guardrails](agent/guardrails-pii-and-hitl.md), [Travel knowledge RAG](agent/rag-travel-knowledge.md) |
| Changing the chat stream, side panels or suggestions | [Agent chat endpoints, SSE streaming and side panels](agent/streaming-and-side-panels.md) and its client twin [Chat widget and streaming client](frontend/chat-and-streaming-client.md) |
| Debugging cost, latency or a run | [Observability, turn metrics and cost](agent/observability-and-metrics.md), [Admin API and server-rendered dashboard](operations/admin-and-dashboard.md) |
| Switching LLM providers or per-agent models | [LLM providers and per-agent configuration](agent/llm-providers-and-agent-config.md) |
| Building a web page or component | [Web app shell, routing and auth](frontend/app-shell-and-routing.md), [Trips, bookings and catalog pages](frontend/trips-bookings-and-catalog-pages.md), [Internationalization and theming](frontend/i18n-and-theming.md) |

## Conventions in one breath

Backend layering is routers → services → repositories with domain exceptions mapped to one JSON envelope; services and routers hold no singletons; async is only for real I/O. Backend commands run from `apps/api/`, frontend commands from `apps/web/` on Node 24. Feature work lives in `specs/<slug>/` with a plan and summary; longer-form decisions are in `docs/decisions/` and learned patterns in `docs/solutions/`. Stage and commit as separate git commands, and target the integration branch for PRs.
