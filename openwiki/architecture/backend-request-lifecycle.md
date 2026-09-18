---
type: architecture
title: Backend request lifecycle
description: How the FastAPI backend boots and serves a request — the app factory and its duplicate-operationId guard, the ordered lifespan startup (schema, seed, config cache, invariants, RAG pre-warm, agent graph), the middleware stack, the single JSON error envelope, the request-scoped session as unit of work, and the routers → services → repositories contract enforced by architecture tests.
tags: [fastapi, lifespan, middleware, dependency-injection, error-handling, layering, unit-of-work, startup]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-3b8ef62288ae24dc8e4a52ed
    resource: repo://apps/api/app/core/deps.py
  - id: openwiki-source-7aeb9f0efe0972a74fa7f984
    resource: repo://apps/api/app/core/errors.py
  - id: openwiki-source-9ebfa83e63167bdfafeebd92
    resource: repo://apps/api/app/core/invariants.py
  - id: openwiki-source-f18f564b85852ec3a8a054dc
    resource: repo://apps/api/app/core/lifespan.py
  - id: openwiki-source-65ac2cabf365dc06842baa77
    resource: repo://apps/api/app/core/middleware.py
  - id: openwiki-source-9967de0445cdfe2a1cd416b6
    resource: repo://apps/api/app/db/engine.py
  - id: openwiki-source-5cef6ea3ac9c60e4fb6d23d3
    resource: repo://apps/api/app/db/session.py
  - id: openwiki-source-317f9c0d55a27936830e7380
    resource: repo://apps/api/app/exceptions.py
  - id: openwiki-source-1bc8bf59d677c1978cc37404
    resource: repo://apps/api/app/main.py
  - id: openwiki-source-9cca1b2482daf25f882222f4
    resource: repo://apps/api/app/repositories/base.py
  - id: openwiki-source-99b09b38bd17883cb804bc24
    resource: repo://apps/api/app/routers/main.py
  - id: openwiki-source-e52f22dd7dfd7d00a70046ae
    resource: repo://apps/api/app/services/trip_service.py
  - id: openwiki-source-c2f2e5401c4873f52ba3d8ee
    resource: repo://apps/api/tests/architecture/test_no_singletons.py
  - id: openwiki-source-d598d758e4ade56fcf2fd37a
    resource: repo://apps/api/tests/infra/test_operation_ids.py
  - id: openwiki-source-f9dd93415b71cf5360e877f1
    resource: repo://techstacks/architecture.md
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Backend request lifecycle

The backend in `apps/api/` is a single FastAPI application whose behaviour is assembled in three places: `app/main.py` (the factory), `app/core/lifespan.py` (startup), and `app/core/middleware.py` plus `app/core/errors.py` (the per-request envelope). Everything below the router layer is plain Python that never imports FastAPI.

## App factory

`create_app()` reads `Settings` once (cached via `lru_cache`; see [Configuration and environments](configuration-and-environments.md)), configures logging, hides `/docs`, `/redoc` and the OpenAPI schema in production, registers exception handlers and middleware, and includes the single aggregate router from `app/routers/main.py`, where every endpoint group is wired in one place (include order only affects Swagger tag order; the two dashboard routers are HTML and excluded from the schema).

The factory sets `generate_unique_id_function` to the handler function name, so **operationIds are stable across refactors**, and then **fails startup if two schema-visible handlers share a name**: a duplicate would silently break the frontend's TypeScript client generation (`tests/infra/test_operation_ids.py`). Module-level `app = create_app()` is what uvicorn and the tests import.

## Startup: the lifespan sequence

`lifespan` runs these steps in order, and the order is deliberate:

1. **Schema.** On SQLite, `Base.metadata.create_all` creates tables; on Postgres nothing is created here because the schema is Alembic-owned (see [Data layer and migrations](data-layer-and-migrations.md)).
2. **Seed** read-only reference data (`seed_all`), idempotent so restarts are safe. This must precede any check that reads it.
3. **Agent config cache**: `AgentConfigCache.configure(...)` wires the loader and poll interval, then an initial `reload_from_db` so per-agent model overrides apply from the first request (see [LLM providers and per-agent configuration](../agent/llm-providers-and-agent-config.md)).
4. **Invariant check**: `check_city_coverage()` raises `RuntimeError` listing offenders if any seeded city has fewer than three hotels or three places, failing loudly at boot rather than at a user's first search.
5. **RAG pre-warm**, wrapped so any failure only logs and the knowledge tool degrades to empty results (see [Travel knowledge RAG](../agent/rag-travel-knowledge.md)).
6. **Per-service `init_db()`** calls for bookings, trips, saved places and the flight index; these are idempotent no-ops on Postgres after Alembic, and any failure here is re-raised because the app cannot serve without them.
7. **Agent graph**: the checkpointer and long-term store are opened as async context managers for the process lifetime, the graph is compiled once and stored on `app.state.travel_graph` together with the backends and the config generation. A graph build failure logs and sets the graph to `None`, which disables the agent endpoints while the rest of the API keeps serving. Rebuilding per request was removed because it leaked a connection.

The `yield` inside the two context managers means the backends close only on shutdown.

## Middleware stack

`register_middleware` declares four `@app.middleware("http")` handlers and two Starlette middlewares. Because decorators register inner-first, the **inbound order is CORS → GZip (bodies ≥ 1000 bytes) → request id → rate-limit headers → access log → route**:

- **Request id**: echoes a caller-supplied `X-Request-ID` or generates one, stores it on `request.state`, and returns it in the response header. It is declared last so it runs earliest and the access log can read it.
- **Rate-limit headers**: after the route runs, writes `X-RateLimit-Limit/Remaining/Reset`. On routes where a limiter actually ran (marked on `request.state`) the real policy values are used; elsewhere a nominal informational limit from settings is reported (see [Rate limiting and quotas](../concepts/rate-limiting-and-quotas.md)).
- **Access log**: the single source of access lines (uvicorn's own access log is silenced), including a `500` line with traceback when a request raises, since the outer error middleware would otherwise swallow it before the normal log line.
- **CORS** is wide open by default for local development; production refuses to boot with a wildcard origin plus credentials (see the configuration page).

## One error envelope

`register_exception_handlers` guarantees that every failure, domain or otherwise, returns the same JSON shape: `error`, `message`, `status_code`, `path`, `request_id` when known, and optional `hint` and `errors`.

- **`AppError` and subclasses** (`app/exceptions.py`) map by their class-level `status_code`: `AuthError` 401, `ForbiddenError`/`PremiumRequiredError` 403, `NotFoundError` 404, `ConflictError`/`DuplicateBookingError` 409, `DomainValidationError` 422, `QuotaExceededError`/`RateLimitError` 429, `UpstreamError` and its weather/routing variants 502. The `error` field is the class name and `hint` is forwarded when set. A `RateLimitError` additionally produces `Retry-After` and hands the policy numbers to the header middleware through `request.state`.
- **Starlette `HTTPException`** (unmatched routes, auth challenges) is relabelled by status code and keeps any headers the raiser attached, such as `WWW-Authenticate` for the dashboard.
- **Any other exception** becomes a 500 envelope with details hidden in production.
- **Request validation** errors return 422 with the per-field `errors` array and a hint on how to read it.

This is what lets services raise domain exceptions and stay free of HTTP concerns.

## The request-scoped session as unit of work

`get_session` (`app/db/session.py`) yields one SQLAlchemy `Session` per request, commits on success, rolls back on any exception and always closes. Engines and session factories are cached per database URL (`app/db/engine.py`) with `pool_pre_ping` so dead Postgres connections are replaced, and SQLite connections allow cross-thread use because a request may cross threadpool workers.

Repositories accept **either** a live `Session` or a `sessionmaker` (`repositories/base.py`). In live mode they only `flush`, so integrity errors surface immediately while the commit is deferred to the request boundary and every repository touched by one request shares one transaction. In factory mode (background tasks, the agent's tool calls, streaming wrappers, startup) they open, commit and close their own session. This is why the agent router commits before invoking the graph and why streaming wrappers use an isolated factory (see [Agent chat endpoints, SSE streaming and side panels](../agent/streaming-and-side-panels.md)).

Services are constructed per request through small dependency functions, for example `get_trip_service`, which binds a `TripService` to the request session and the authenticated caller's id so every query is owner-scoped. The architecture test `tests/architecture/test_no_singletons.py` forbids module-level repository or service singletons and `set_*_repo` mutators in `services/` and `routers/`, so tests override exactly one dependency, `get_session`, to point the whole app at a temporary database (see [Backend test strategy](../testing/backend-test-strategy.md)). The LLM client follows the same pattern through `get_llm_client`.

## The layering contract

`techstacks/architecture.md` states the rule the code follows: **routers → services → repositories**, with no use-case layer.

- **Routers** are HTTP only: validate input, resolve dependencies, delegate, return a Pydantic schema. No business logic and no ORM.
- **Services** hold the business logic and raise domain exceptions, never `HTTPException`. They receive a session (and usually a user id) and build repositories on it.
- **Repositories** are the only place ORM models are touched; they return schema objects or ORM rows that services convert.
- **Agents, tools and the MCP server** are thin adapters over services with no business logic of their own (see [Specialist sub-agents and the tool registry](../agent/specialists-and-tools.md)).
- Async is used only for real network I/O (weather, routing, the agent); everything else is synchronous.

Liveness and readiness live in `routers/health.py` (`/healthz` is static, `/readyz` touches the booking store) and `/` returns service info with the endpoint list.
