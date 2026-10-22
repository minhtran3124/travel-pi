---
type: architecture
title: LLM providers and per-agent configuration
description: How chat models are built provider-agnostically, the static provider catalog with per-provider API keys and gateway base URLs, the fast vs full model tiers, DB-backed per-agent overrides served through a poll-refreshed in-process cache that triggers a graph rebuild, and the deterministic FakeLLM used by the test suite.
tags: [llm, providers, agent-config, cache, openai, anthropic, gemini, fake-llm, configuration]
sources:
  - id: openwiki-source-653637f2675661d4499c6d01
    resource: repo://apps/api/app/agents/constants.py
  - id: openwiki-source-a9279e30fdd03870c290e7ae
    resource: repo://apps/api/app/agents/graph.py
  - id: openwiki-source-0a4654a64cce509bb5ebd3e2
    resource: repo://apps/api/app/clients/llm.py
  - id: openwiki-source-b33173c12a0f88ac95561cd2
    resource: repo://apps/api/app/core/agent_config_cache.py
  - id: openwiki-source-f18f564b85852ec3a8a054dc
    resource: repo://apps/api/app/core/lifespan.py
  - id: openwiki-source-a8e495fdc04a0eb3a7eab2c3
    resource: repo://apps/api/app/core/llm_providers.py
  - id: openwiki-source-46b62ea48d340bf2a955b42b
    resource: repo://apps/api/app/core/pricing.py
  - id: openwiki-source-f7da211cb9484fe97dbad3af
    resource: repo://apps/api/app/db/models/agent_config.py
  - id: openwiki-source-dd51ce6041b0216bb8b46bef
    resource: repo://apps/api/app/db/seed.py
  - id: openwiki-source-798ba55c4480c62612a305f8
    resource: repo://apps/api/app/research/agent.py
  - id: openwiki-source-40fb538510ad8b559a8e282e
    resource: repo://apps/api/app/routers/agent.py
  - id: openwiki-source-7398073c9f62630d454539d1
    resource: repo://apps/api/app/services/agent_config_service.py
  - id: openwiki-source-106bef8b59a5a8a8430af871
    resource: repo://apps/api/scripts/seed_agent_config.py
  - id: openwiki-source-425792685e8260732326a064
    resource: repo://apps/api/tests/agents/test_agent_config_coverage.py
  - id: openwiki-source-e3ec59830061b535cdcd7789
    resource: repo://apps/api/tests/agents/test_graph_refresh.py
  - id: openwiki-source-feda39a40fba08eb926ae85a
    resource: repo://apps/api/tests/clients/test_get_agent_llm_db_config.py
  - id: openwiki-source-ff8abdeb0845cd61acef9f4b
    resource: repo://apps/api/tests/clients/test_llm_max_retries.py
  - id: openwiki-source-95c069bc84abac486d7a352a
    resource: repo://apps/api/tests/clients/test_llm_stream_usage.py
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
---

# LLM providers and per-agent configuration

Every graph node that calls a model resolves it through `get_agent_llm(name)` in `apps/api/app/clients/llm.py`. That one function layers three sources of truth: the global settings (`LLM_PROVIDER`, `LLM_MODEL`, `FAST_LLM_MODEL`, see [Configuration and environments](../architecture/configuration-and-environments.md)), the static provider catalog, and a per-agent override row in the `agent_config` table edited from the dashboard (see [Admin API and dashboard](../operations/admin-and-dashboard.md)).

## Building a chat model

`_build_chat_model(provider, model, temperature=None, base_url=None, **extra)` wraps `langchain.chat_models.init_chat_model` and has no import-time side effects (`tests/clients/test_llm.py::test_import_has_no_side_effects`). The rules it applies:

- **The provider name is resolved against the catalog** in `app/core/llm_providers.py`, but the catalog is a reference list, not an allowlist: an unknown name falls back to a bare profile whose SDK is the name itself.
- **Each profile owns its own API-key setting** (`openai_api_key`, `anthropic_api_key`, `google_api_key`, `clinepass_api_key`, `claude_api_key`); keys are never shared across providers, and an import-time assertion fails loudly if a profile lacks a key field.
- **Base URL precedence** is explicit per-agent argument, then the profile's gateway URL, then the global `LLM_BASE_URL`. Gateway profiles (`clinepass`, `claude`) reuse a native SDK (`openai`, `anthropic`) against a custom host; native profiles carry no base URL.
- **`temperature` and extra kwargs are forwarded only when set**, so reasoning models that reject them still work.
- **`max_retries` defaults to 0** because the graph owns retries through its node retry policy; SDK-level retries would double up.
- **OpenAI-SDK models request `stream_usage=True`**, otherwise streamed calls return no usage metadata and the turn metrics would be blind (`tests/clients/test_llm_stream_usage.py`).
- All models are built with `streaming=True`.

`get_llm(model=None, fast=False)` builds the global default; `fast=True` selects `fast_llm_model`.

## Fast vs full tiers

`FAST_AGENTS` in `app/agents/constants.py` names the nodes that default to the cheap model when no override sets one: `summarize`, `journal`, `budget`, `reflection`, `extract_memory`, `date_resolution`, `trip_research_grader`. Everything else (`supervisor`, `planner`, `concierge`, `booking`, `synthesize`) defaults to the full model. The graph builder uses the same set to decide whether an injected `fast_llm` or `llm` fake should stand in for a node during tests (see [Agent graph and supervisor routing](graph-and-supervisor.md)).

## Per-agent overrides from the database

`get_agent_llm(agent_name)` asks `AgentConfigCache.get(agent_name)`. With no row the behaviour is exactly `get_llm(fast=...)`. With a row, resolution is **per field**: provider, model, base URL, temperature and `max_tokens` each fall back individually to the global default when the column is `NULL`, so a row that sets only the provider still inherits the tier's default model (`tests/clients/test_get_agent_llm_db_config.py`).

The `agent_config` ORM model (`app/db/models/agent_config.py`) has one row per `agent_name` (unique index) with nullable `provider`, `model`, `base_url`, `temperature`, `max_tokens` and `enabled`. `enabled=None` means enabled; only an explicit `False` disables. Today the only consumer of `enabled` is the `reflection` node: the agent router reads it when resolving the per-run `AgentContext` and maps it to `allow_reflection`, which the reflection node honours.

The set of configurable node names lives in `app/data/agent_config.py` (`AGENT_CONFIG_GROUPS` → `AGENT_CONFIG_NODES`: the supervisor, the five specialists, and the support nodes `summarize`, `reflection`, `extract_memory`, `date_resolution`, `synthesize`). `AgentConfigService.list_configs` always returns one view per known node, merged with whatever rows exist, and `update_config` validates the provider against `PROVIDER_NAMES`, temperature within 0–2, `max_tokens` ≥ 1, upserts, and then calls `AgentConfigCache.invalidate()`. The dashboard hides `base_url` and derives it from the provider profile, so the service always stores `NULL` there.

The two trip-research nodes, `trip_research` (the deep agent) and `trip_research_grader` (its rubric grader), are not in `AGENT_CONFIG_GROUPS`. `_seed_research_agent_config` in `app/db/seed.py` seeds them separately by **mirroring a sibling's effective config**: `trip_research` copies `planner`, and `trip_research_grader` copies the fast `summarize` row. Where the sibling's column is NULL, the tier-appropriate global default (`llm_model` or `fast_llm_model`) is used. So these rows are never seeded with a NULL model, which would 403 at the provider boundary. The mirror also fixes the tier, because a concrete row value wins over the `FAST_AGENTS` fallback. Seeding is idempotent and never overwrites an existing row. See [Trip-research deep agent](trip-research-deep-agent.md).

`tests/agents/test_agent_config_coverage.py` scans the source for every string literal passed to `get_agent_llm` or `pick` and asserts each has a config row name, so a new model-resolving node (including a tool that makes its own LLM call, like `date_resolution`) cannot ship without being configurable. The research rows count as covered through `_RESEARCH_AGENT_MIRRORS`. `synthesis_worker` is the deliberate exception: it resolves the specialist's own name at runtime rather than its own. The promptless `research` launcher node is also excluded, because it never calls a model.

## The cache and the graph rebuild

`AgentConfigCache` (`app/core/agent_config_cache.py`) is process-wide and poll-refreshed:

- The lifespan calls `configure(session_factory, poll_interval)` and an initial `reload_from_db` so overrides apply from the first request.
- Every `get()` / `generation()` first runs `_maybe_refresh()`: past the poll interval (`AGENT_CONFIG_POLL_INTERVAL_SECONDS`) it does a cheap `max_updated_at()` probe and reloads only when that timestamp changed or the cache was explicitly invalidated. Any `SQLAlchemyError` logs and serves the last-known-good cache rather than raising into the request path; a pending invalidation survives a failed poll.
- `sync_from_cache` bumps the **generation counter only when the data actually changed**. The interval check is lock-free; the refresh path is serialized by a lock so a slow thread cannot overwrite a fresher reload.

`resolve_travel_graph(app)` in `app/agents/graph.py` compares `AgentConfigCache.generation()` with the generation stamped on `app.state.travel_graph_gen`; when they differ it rebuilds the graph **reusing the process-lifetime checkpointer and store**, so conversation state survives a config change. A failed rebuild keeps the previous graph. `tests/agents/test_graph_refresh.py` pins that the rebuild happens only on a generation change and that a graph without stashed backends is served as-is.

Operationally, startup seeding creates one all-NULL row per node in `AGENT_CONFIG_NODES`, so the service inherits the env globals. The two research rows are the exception and carry concrete values, as described above. The trip-research agent is built once in lifespan and is not rebuilt by `resolve_travel_graph`, so a change to its row takes effect on the next process start. For the rest, `python -m scripts.seed_agent_config` is the idempotent way to flip a deployment to DB-driven config, after which the running app picks the change up on its next poll.

## Cost estimation

`app/core/pricing.py` holds a static USD-per-million-token table per model (OpenAI, Anthropic, Google, verified against provider pricing pages on a recorded date). `estimate_cost(by_model)` sums input, output and cached-input costs and returns `None`, never a false `0.0`, when the input is empty or any model is missing from the table; dated snapshot suffixes are normalized away. The per-turn metrics handler uses it to record a cost on each `agent_runs` row (see [Observability, turn metrics and cost](observability-and-metrics.md)).

## `FakeLLM` for tests

`FakeLLM` is a `BaseChatModel` that cycles through scripted `responses` (strings, `AIMessage`s, or dicts with `tool_calls`) and `structured_responses`, with zero network. `bind_tools` is a no-op because scripted tool calls drive the `ToolNode`; `with_structured_output` returns a runnable that yields the next structured item. Each generated message carries deterministic usage metadata (10 input, 5 output tokens, model `fake-llm`) so offline turns still exercise the token, cost and latency metrics path. Tests inject it either through `build_graph(llm=..., fast_llm=...)` or by overriding the FastAPI dependency; see [Backend test strategy](../testing/backend-test-strategy.md).
