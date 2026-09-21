---
type: reference
title: Configuration and environments
description: The pydantic-settings Settings model that drives the backend, every environment-variable group (database, external travel APIs, CORS, rate limits, LLM providers and keys, Langfuse, agent runtime knobs, dashboard auth, Supabase), what changes between development and production, the frontend's public variables, and how the Docker dev and test stacks inject their own values.
tags: [configuration, environment-variables, settings, docker, postgres, sqlite, production, supabase]
sources:
  - id: openwiki-source-5df10578b47a3ab545818aba
    resource: repo://apps/api/.env.example
  - id: openwiki-source-5300fab0b97a7cfb93201ea7
    resource: repo://apps/api/app/core/config.py
  - id: openwiki-source-eda0b38a403232caa7fc52bf
    resource: repo://apps/api/app/core/dashboard_auth.py
  - id: openwiki-source-e2525d77332a0331e3e20d83
    resource: repo://apps/api/app/core/logging.py
  - id: openwiki-source-005fa33a80365b59c59a2523
    resource: repo://apps/api/docker-compose.test.yml
  - id: openwiki-source-555487c3c39cc1f3039be31e
    resource: repo://apps/api/docker-compose.yml
  - id: openwiki-source-c67fada0a467b1fb8d2dec3a
    resource: repo://apps/api/docker/entrypoint.sh
  - id: openwiki-source-aa075c7c44459db4084deeb3
    resource: repo://apps/api/Dockerfile
  - id: openwiki-source-2ac05ad00ebc6a0920aa84b7
    resource: repo://apps/api/tests/core/test_config_llm.py
  - id: openwiki-source-37186b9bfb98e1af333ad420
    resource: repo://apps/web/.env.example
generated: { by: "claude-code", at: "2026-09-21T09:19:54.601Z" }
verified:
  - by: openwiki/0.5.2
    at: 2026-09-21T09:19:54.601Z
---

# Configuration and environments

All backend configuration is one `Settings` class in `apps/api/app/core/config.py`, built on `pydantic-settings`. It reads environment variables, falls back to a local `.env` file in `apps/api/`, ignores unknown keys, and gives **every value a dev-safe default**, so the API runs with no `.env` at all: SQLite, fake embeddings, no auth verification, no tracing. `get_settings()` is `lru_cache`d, so settings are read once per process; tests that need different values monkeypatch or clear that cache. `apps/api/.env.example` documents each variable with its default and is the reference for operators.

## Variable groups

**Environment and server.** `ENVIRONMENT` is a `Literal` of `development`, `production`, `test` (normalized to lower case; a typo fails startup rather than silently running in dev). `LOG_LEVEL` is upper-cased and validated. `HOST`/`PORT` and the OpenAPI metadata (`APP_NAME`, `APP_DESCRIPTION`, `APP_VERSION`) round out the group. Logging (`app/core/logging.py`) installs one console handler and format for the whole process and silences `uvicorn.access`, because the request-logging middleware is the single source of access lines (see [Backend request lifecycle](backend-request-lifecycle.md)).

**Database.** `DATABASE_URL` defaults to `sqlite:///travel.db`; the engine, the LangGraph checkpointer, the long-term memory store and the RAG vector store all select their backend from this one value, and every non-Postgres URL degrades agent persistence to in-memory (see [Data layer and migrations](data-layer-and-migrations.md) and [Conversation memory and persistence](../agent/memory-and-persistence.md)).

**External travel data.** Weather, climate normals and air quality use keyless Open-Meteo endpoints (`WEATHER_*`, `CLIMATE_YEARS`, `AIR_QUALITY_FORECAST_DAYS`). Routing uses OpenRouteService only when `ORS_API_KEY` is set (`routing_provider_enabled`); unset, `/places/route` falls back to an offline haversine estimate. See [Destinations, places and travel information](../domain/destinations-places-and-travel-info.md).

**CORS.** Wide open by default (`["*"]` origins, methods and headers, credentials allowed). A model validator **refuses to start in production with a wildcard origin and credentials enabled**, forcing explicit `CORS_ORIGINS`.

**Rate limits.** `RATE_LIMIT_NOMINAL` is informational only, advertised in headers so clients can self-throttle. `FEEDBACK_RATE_LIMIT_MAX` / `FEEDBACK_RATE_LIMIT_WINDOW_SECONDS` are the enforced DB-backed policy for feedback (see [Rate limiting and quotas](../concepts/rate-limiting-and-quotas.md)).

**LLM providers.** `LLM_PROVIDER` must be a profile name from the provider catalog (`openai`, `anthropic`, `google_genai`, or the `clinepass` / `claude` gateways); an unknown name fails validation. `LLM_MODEL` and `FAST_LLM_MODEL` are the full and cheap tiers, `EMBEDDING_MODEL` the embedding model, `LLM_BASE_URL` a catch-all gateway host used only by profiles without their own. Each profile reads **only its own key** (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `CLINEPASS_API_KEY`, `CLAUDE_API_KEY`); no key is required because tests and keyless dev use `FakeLLM`. Embeddings never go through a gateway, so RAG and semantic memory need a real provider key. Per-agent overrides live in the database, not in env (see [LLM providers and per-agent configuration](../agent/llm-providers-and-agent-config.md)). `EVAL_EXTRACTOR_MODEL` configures the eval oracle's extractor and is deliberately not an agent-config row.

**Langfuse.** `LANGFUSE_ENABLED` defaults to false so CI emits no traces and needs no keys; `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` apply when enabled.

**Agent runtime.** `AGENT_RECURSION_LIMIT` (25) bounds each graph invocation, `SUMMARIZE_THRESHOLD` (20 messages) or `SUMMARIZE_TOKEN_BUDGET` (12000, compared at 85% against a character-based token estimate) triggers history compression, `AGENT_FREE_DAILY_TURN_LIMIT` (20) is the free-tier quota, `AGENT_CONFIG_POLL_INTERVAL_SECONDS` (5) governs the config cache refresh and still accepts the legacy name `AGENT_CONFIG_CACHE_TTL_SECONDS` through an alias, and `AGENT_TIMEZONE` (`Asia/Ho_Chi_Minh`) grounds "today" when a client sends no valid timezone.

**Dashboard.** `DASHBOARD_BASIC_USER` and `DASHBOARD_BASIC_PASSWORD` enable HTTP Basic on every `/dashboard/*` route, compared in constant time. With neither set, the dashboard is open in development but returns 404 in production, so it is never reachable in production without credentials (see [Admin API and server-rendered dashboard](../operations/admin-and-dashboard.md)).

**Supabase.** JWT verification is off until `SUPABASE_URL` or `SUPABASE_PROJECT_REF` is set; the JWKS URL and expected issuer are derived from either (`resolved_jwks_url`, `resolved_jwt_issuer`) with `SUPABASE_JWKS_URL` / `SUPABASE_JWT_ISSUER` as explicit overrides for self-hosted projects, and `SUPABASE_JWT_AUDIENCE` defaults to `authenticated`. The service-role key is only needed by operational scripts (see [Authentication and user tiers](../concepts/auth-and-tiers.md)).

## Development versus production

`is_production` is the single switch, and it changes exactly these behaviours: interactive docs and the OpenAPI schema are hidden; unexpected-exception messages are replaced by a generic "Internal server error"; the dashboard 404s without credentials; a wildcard-CORS-with-credentials configuration refuses to boot; and a configured-but-unreachable Postgres makes the agent checkpointer refuse to start instead of degrading to an ephemeral in-memory saver. Everything else is identical across environments.

## Where values come from in each runtime

| Runtime | Database | How settings arrive |
|---|---|---|
| Local `make api` / pytest | SQLite file, or `TEST_DATABASE_URL` for the suite | `apps/api/.env` if present, else defaults; tests override `get_session` to a temp SQLite file |
| `docker compose up` (dev) | `pgvector/pgvector:pg17` on host port 5433 with a persistent volume | `env_file: .env` plus a compose override of `DATABASE_URL` to the `db` service and `ENVIRONMENT=development`; the source tree is bind-mounted and uvicorn runs with `--reload` |
| `docker compose -f docker-compose.test.yml` | `postgres:17-alpine` on tmpfs, wiped on teardown | `DATABASE_URL` and `TEST_DATABASE_URL` both point at the test database so the same pytest suite runs against Postgres after `alembic upgrade head` |

The image (`Dockerfile`, Python 3.12 slim) installs `requirements.txt`, which pulls in the LangChain stack from `requirements-ai.txt`, and its entrypoint always runs `alembic upgrade head` before starting the server; that is a no-op on SQLite, whose schema the lifespan creates itself. Note the Docker image runs Python 3.12 while local development may use a newer interpreter, so `make test-docker` is the parity check. See [Local development, Docker and CI](../operations/local-dev-docker-and-ci.md).

## Frontend variables

`apps/web/.env.example` lists the public variables the Next.js app needs: `NEXT_PUBLIC_API_URL` (the FastAPI origin, proxied at `/api/be/*` and used directly for agent SSE, default `http://localhost:8000`), and `NEXT_PUBLIC_SUPABASE_URL` plus `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, which are required because the browser, server and middleware Supabase clients are constructed against them even in local development. `E2E_USER_EMAIL` / `E2E_USER_PASSWORD` are read only by the Playwright runner; absent, the e2e specs skip (see [Frontend unit tests and Playwright e2e](../testing/frontend-tests-and-e2e.md)).
