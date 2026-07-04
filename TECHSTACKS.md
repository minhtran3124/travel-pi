# TECHSTACKS.md

> The technology stack for both apps in this monorepo, with versions sourced from the
> actual manifests (`package.json`, `requirements*.txt`, `pyproject.toml`).
> Companion to `AGENTS.md` (orientation) and `README.md` (setup). Last verified: 2026-06-26.

---

## Monorepo tooling

| Concern | Choice | Version | Source |
|---|---|---|---|
| Package manager (JS) | **pnpm** (workspaces) | `11.9.0` | root `package.json` → `packageManager` |
| Task runner / build orchestration | **Turborepo** | `^2` | root `package.json`, `turbo.json` |
| Node runtime | **Node.js** | `>=20` | root `package.json` → `engines` |
| Python runtime | **Python** | `>=3.10` (lint target `py310`) | `apps/api/pyproject.toml` |
| Python env / installer | **uv** + single root `.venv` | — | `README.md`, `apps/api/Makefile` |

Turbo pipeline (`turbo.json`): `build` (depends on upstream `^build`, caches `.next/`, `dist/`),
`dev` (persistent, uncached), `lint`, `test` (depends on `^build`).

---

## Frontend — `apps/web` (`@travel/web`)

| Concern | Choice | Version |
|---|---|---|
| Framework | **Next.js** (App Router) | `16.2.9` |
| UI library | **React** + React DOM | `19.2.4` |
| Language | **TypeScript** | `^5` |
| Styling | **Tailwind CSS** (v4, via `@tailwindcss/postcss`) | `^4` |
| Server state / data fetching | **TanStack Query** (`@tanstack/react-query`) | `^5.101` |
| API client | **openapi-fetch** (typed against the BE OpenAPI schema) | `^0.17` |
| API types codegen | **openapi-typescript** | `^7.13` |

**Testing & quality**

| Concern | Choice | Version |
|---|---|---|
| Unit/component tests | **Vitest** + `@vitejs/plugin-react` | `^2.1` |
| DOM testing | **Testing Library** (`react`, `jest-dom`) + **jsdom** | `^16.1` / `^6.6` / `^25` |
| API mocking | **MSW** (Mock Service Worker) | `^2.7` |
| E2E | **Playwright** (`@playwright/test`) | `^1.49` |
| Lint | **ESLint** + `eslint-config-next` | `^9` / `16.2.9` |

**Key scripts** (`apps/web/package.json`): `dev`, `build`, `start`, `lint`, `test` (vitest),
`e2e` (playwright), `gen:api` (regenerate `schema.d.ts` from `http://localhost:8000/openapi.json`).

**Wiring:** the API client uses a relative `baseUrl` `"/api/be"`; `next.config.ts` rewrites
`/api/be/:path*` to the backend (`NEXT_PUBLIC_API_URL`, default `http://localhost:8000`).

---

## Backend — `apps/api`

FastAPI mock backend. Everything faked except keyless Open-Meteo (`/weather`, `/air-quality`,
climate), `/*/route` (OpenRouteService + haversine fallback), and the AI agent's LLM calls
(real provider via `init_chat_model()` when keys are set; `FakeLLM` in tests).

**Core framework & data** (`apps/api/requirements.txt`)

| Concern | Choice | Version |
|---|---|---|
| Web framework | **FastAPI** | `>=0.110,<0.137` ⚠ |
| ASGI toolkit | **Starlette** | `>=0.40,<1.3` ⚠ |
| ASGI server | **Uvicorn** (`[standard]`) | `>=0.27,<1.0` |
| Validation / models | **Pydantic v2** + **pydantic-settings** | `>=2.6,<3.0` / `>=2.2,<3.0` |
| Email validation | **email-validator** (backs `EmailStr`) | `>=2.0,<3.0` |
| Templating | **Jinja2** (dashboard templates) | `>=3.1,<4.0` |
| HTTP client | **httpx** (async; weather/routing calls) | `>=0.28,<1.0` |
| ORM | **SQLAlchemy 2.x** | `>=2.0,<2.1` |
| Postgres driver | **psycopg 3** (`postgresql+psycopg://`) | `>=3.1,<4.0` |
| Migrations | **Alembic** | `>=1.13,<2.0` |
| Local DB | **SQLite** (file `travel.db`) | stdlib |
| Container/prod DB | **PostgreSQL** (via Docker) | — |

> ⚠ **FastAPI/Starlette caps are deliberate.** Held below FastAPI 0.137 / Starlette 1.3 because
> newer route-introspection breaks operation-id / route-enumeration tests. Do not bump these to
> satisfy a transitive AI dep — escalate instead (see `requirements-ai.txt` note).

**AI / Agent layer** (`apps/api/requirements-ai.txt`)

| Concern | Choice | Version |
|---|---|---|
| Agent graph runtime | **LangGraph** | `>=1.0,<2.0` |
| LLM framework | **LangChain** | `>=1.0,<2.0` |
| LLM providers | **langchain-openai** / **langchain-anthropic** (provider-agnostic via `init_chat_model()`) | `>=0.3,<1.0` / `>=1.0,<2.0` |
| Checkpointers | **langgraph-checkpoint-sqlite** / **-postgres** | `>=3.0,<4.0` |
| Observability | **Langfuse** (optional, off by default) | `>=3.0,<5.0` |
| Tool exposure | **MCP** (Model Context Protocol server) | `>=1.2,<2.0` |

Default models (`app/core/config.py`): `gpt-4.1` (reasoning), `gpt-4.1-mini` (fast),
`text-embedding-3-small` (embeddings). See `WORKFLOW.md` for the agent architecture.

**Testing & quality**

| Concern | Choice | Version |
|---|---|---|
| Test runner | **pytest** | `>=9.0,<10.0` |
| Lint + format | **Ruff** | `>=0.15,<1.0` |
| Cross-engine parity | tests run on **SQLite** (`make test`) and **Postgres** (`make test-docker`) | — |

---

## At a glance

```
Monorepo:  pnpm workspaces + Turborepo
           Node >=20  ·  Python >=3.10 (uv, root .venv)

apps/web   Next.js 16 · React 19 · TypeScript 5 · Tailwind 4
           TanStack Query · openapi-fetch  ──/api/be/*──▶  apps/api
           Vitest · Testing Library · MSW · Playwright · ESLint

apps/api   FastAPI · Starlette · Uvicorn · Pydantic v2
           SQLAlchemy 2 · Alembic · SQLite/Postgres (psycopg 3)
           LangGraph 1 · LangChain 1 · OpenAI/Anthropic · pgvector · MCP · Langfuse
           pytest · Ruff
```

> Version policy: dependencies are pinned to the **current major** (upper-bounded) so a fresh
> install can't pull a breaking release. Loosen caps only after validating — and never bump the
> FastAPI/Starlette caps to satisfy a transitive AI dependency.
