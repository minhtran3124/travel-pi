---
type: testing
title: Backend test strategy
description: How the FastAPI backend is tested — the pytest layout by layer, the session-scoped client fixture that swaps exactly two dependencies (the database session and the authenticated user) to run the real app against a temporary SQLite file or a Postgres URL, the fixtures that repoint settings for tools and RAG, the deterministic FakeLLM and graph injection that keep agent tests offline, the architecture tests that enforce layering and language conventions, environment pitfalls, and the Docker Postgres run that proves cross-engine parity.
tags: [testing, pytest, fixtures, fake-llm, sqlite, postgres, architecture-tests, backend]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-41b70976e433ce7b0af3f31e
    resource: repo://apps/api/app/services/weather_service.py
  - id: openwiki-source-005fa33a80365b59c59a2523
    resource: repo://apps/api/docker-compose.test.yml
  - id: openwiki-source-b2697db94ca37e702a50682a
    resource: repo://apps/api/pyproject.toml
  - id: openwiki-source-51bfe609ddfa0879e7b6d4b2
    resource: repo://apps/api/scripts/test-docker.sh
  - id: openwiki-source-a51b21223e4db622d68dd052
    resource: repo://apps/api/tests/agents/test_graph.py
  - id: openwiki-source-f3a3c32caa6033d078172527
    resource: repo://apps/api/tests/api/agent/test_agent_chat.py
  - id: openwiki-source-d37fd6d17e938910eb74dc7b
    resource: repo://apps/api/tests/architecture/test_feedback_no_memory_edge.py
  - id: openwiki-source-a50b62cfcd86c99f1415437e
    resource: repo://apps/api/tests/architecture/test_language_literals.py
  - id: openwiki-source-c2f2e5401c4873f52ba3d8ee
    resource: repo://apps/api/tests/architecture/test_no_singletons.py
  - id: openwiki-source-3a2dde6adaa0b4f58984ea0b
    resource: repo://apps/api/tests/conftest.py
  - id: openwiki-source-7fb2c836f6ede44abc447fd6
    resource: repo://apps/api/tests/db/test_session.py
  - id: openwiki-source-40248636edebdb53838d13f7
    resource: repo://apps/api/tests/rag/conftest.py
  - id: openwiki-source-205128f194082ee3dd5bbb77
    resource: repo://apps/api/tests/tools/conftest.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Backend test strategy

The backend suite under `apps/api/tests/` is fast, offline and zero-config: `make test` runs it on a temporary SQLite file with no `.env`, no LLM key and no network, and `make test-docker` runs the identical suite on Postgres. CI runs the SQLite path on every pull request (see [Local development, Docker and CI](../operations/local-dev-docker-and-ci.md)).

## Layout

Tests are grouped by layer rather than by feature: `api/` (endpoint tests per domain, plus `agent/`, `agent_config/`, `admin/`, `auth/`), `services/`, `repositories/`, `db/` (models, seeding, migrations, determinism goldens), `tools/`, `agents/` (about fifty files covering routing, HITL, memory, reflection, tier gating, PII, fault tolerance and prompt versions), `memory/`, `streaming/`, `rag/`, `prompts/`, `mcp/`, `clients/`, `core/`, `infra/` (middleware, errors, health, operation ids, rate-limit headers), `unit/`, `eval/` (the eval engine's own tests, see [Agent evaluation harness](agent-eval-harness.md)) and `architecture/`. Ruff formats tests the same way as application code but only `app` and `scripts` are lint-gated.

## The client fixture: real app, two overrides

`tests/conftest.py` defines a session-scoped `tmp_db` (a temp SQLite file, or `TEST_DATABASE_URL` when set) and a session-scoped `client`. The client creates the schema, runs the idempotent seeder, upserts the shared caller `test-user-1` as **premium** so book-route tests are not gated to 403, builds the real app with `create_app()` and overrides exactly two dependencies:

- `get_session` → a generator over the temp database with the same commit/rollback/close contract as production;
- `get_current_user` → a fixed `AuthUser`, because Supabase is not configured in tests.

Everything else (middleware, error envelope, routers, services, repositories, lifespan startup including seeding, invariants and graph build) runs for real. This works only because the app has no module-level service or repository singletons, which `tests/architecture/test_no_singletons.py` enforces, so repointing one session dependency repoints the whole app (see [Backend request lifecycle](../architecture/backend-request-lifecycle.md)). Tests that need a different caller, a free tier or an anonymous request override or clear `get_current_user` locally; `tests/api/auth/test_jwt_auth.py` exercises real verification with an in-process RSA key and a monkeypatched JWKS client (see [Authentication and user tiers](../concepts/auth-and-tiers.md)).

An autouse fixture clears the process-wide geocode cache around every test, because `weather_service` memoizes successful geocodes for the life of the process and a leak would make tests order-dependent. `seeded_session` yields a session on the seeded temp database for unit tests that call services directly, and `booking_service` binds a `BookingService` to a fresh session.

## Fixtures that repoint settings

Agent tools and the RAG store do not receive a request session; they read `get_settings().database_url` and open their own. `tests/tools/conftest.py::agent_db` therefore sets `DATABASE_URL` to a fresh seeded temp database and clears the settings cache, `trip_id` creates a trip on it, and `reset_store` clears the URL-keyed vector-store cache and forces fake embeddings so a stale store cannot leak across temp databases and a real key in `.env` never reaches OpenAI. `tests/rag/conftest.py` does the same for retrieval tests. `tests/db/test_session.py` pins the session dependency's commit, rollback and close behaviour.

## Keeping the agent offline

`FakeLLM` (`app/clients/llm.py`) is a scripted chat model: `responses` drive prose and tool calls, `structured_responses` drive the supervisor's structured output, and every message carries deterministic usage metadata so the metrics path is exercised (see [LLM providers and per-agent configuration](../agent/llm-providers-and-agent-config.md)). Agent tests build the graph with `build_graph(llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore())`, injecting fakes for both tiers. API-level agent tests (`tests/api/agent/`) build the graph **once per app** and override the `get_travel_graph` dependencies with it, deliberately not `app.state.travel_graph`, because a per-request rebuild would lose the in-memory checkpointer and break HITL resume. Streaming tests feed synthetic event iterators through the persistence and run-recording wrappers.

## Architecture tests

`tests/architecture/` holds executable conventions: no module-level repository or service singletons or `set_*_repo` mutators in `services/` and `routers/`; no inline `"en"`/`"vi"` literals in the agent modules, so `app/core/languages.py` stays the single owner; and no static import edge from the feedback write path to any memory module or the LangGraph store package, so feedback can never change memory. `tests/infra/test_operation_ids.py` asserts operation ids equal handler names and that a duplicate fails startup; `tests/core/test_languages.py` parity-tests the backend language list against the frontend config; `tests/agents/test_agent_config_coverage.py` asserts every model-resolving node has a config row; `tests/agents/test_prompt_map.py` asserts prompt attribution covers exactly the graph's nodes.

## Environment pitfalls

- A real key or a Postgres URL in `apps/api/.env` can redden the suite, because settings read `.env`; fixtures that must be hermetic blank `OPENAI_API_KEY` and repoint `DATABASE_URL` explicitly, and `env -u` is not enough because `.env` wins. The eval harness treats `OPENAI_API_KEY=test` as a placeholder for the same reason.
- After an ORM schema change, a stale local `travel.db` breaks the suite on the SQLite path because that schema is created, never migrated; delete and rebuild it.
- Seed default changes are invisible on an existing database, since the seeder merges by stable id; verify them on a fresh temp database.
- The Docker image runs Python 3.12 while a local interpreter may be newer; a builtin shadowed by a local name that is also used as an annotation fails only under eager annotations, so run `make test-docker` before claiming cross-engine parity.

## Running

From `apps/api/`: `../../.venv/bin/python -m pytest tests/ -q` for the suite, or a single file with `-xvs`. `make test-docker` builds the image, starts a tmpfs Postgres, migrates with Alembic and runs the same suite with `TEST_DATABASE_URL` set, then tears everything down. Determinism goldens in `tests/db/test_determinism.py` are what make the two runs comparable byte for byte (see [Data layer and migrations](../architecture/data-layer-and-migrations.md)).
