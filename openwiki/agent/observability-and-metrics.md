---
type: architecture
title: Observability, turn metrics and cost
description: How each agent turn is measured and recorded — the per-turn TurnMetricsHandler callback that collects token, latency, node-timing and step data without ever storing user content, the agent_runs and agent_run_steps tables, USD cost estimation, prompt-version attribution per step, optional Langfuse tracing, and the prompt-cache reporting scripts.
tags: [observability, metrics, langfuse, agent-runs, cost, tokens, prompt-cache, tracing]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
sources:
  - id: openwiki-source-21bdb8ea18207c93e4e44b5e
    resource: repo://apps/api/app/agents/metrics.py
  - id: openwiki-source-1ebfeb0b2d43d1c3077b8e0e
    resource: repo://apps/api/app/agents/observability.py
  - id: openwiki-source-601069c231d7cd08336d73cc
    resource: repo://apps/api/app/agents/prompt_map.py
  - id: openwiki-source-1b2f1dae51bc73b63c3ac802
    resource: repo://apps/api/app/db/models/agent_run_step.py
  - id: openwiki-source-bc2495e3788146e0e97f0051
    resource: repo://apps/api/app/db/models/agent_run.py
  - id: openwiki-source-01ada6c906adfc14310537d1
    resource: repo://apps/api/app/repositories/agent_run.py
  - id: openwiki-source-69b5620a4514fcbadef1ab2e
    resource: repo://apps/api/app/research/runner.py
  - id: openwiki-source-b842553da9494f6fbfc62431
    resource: repo://apps/api/app/research/service.py
  - id: openwiki-source-40fb538510ad8b559a8e282e
    resource: repo://apps/api/app/routers/agent.py
  - id: openwiki-source-df7557ff84d3b69d14466bfe
    resource: repo://apps/api/app/streaming/agent_run.py
  - id: openwiki-source-942521cf1a089501ef72051b
    resource: repo://apps/api/scripts/cache_hit_report.py
  - id: openwiki-source-3f7aa65614c8f0737ad95ca9
    resource: repo://apps/api/scripts/probe_cache_retention.py
  - id: openwiki-source-61c11a19506ba2b84aa7984a
    resource: repo://apps/api/tests/agents/test_observability.py
  - id: openwiki-source-45f7c6785f2398687b91166b
    resource: repo://apps/api/tests/agents/test_turn_metrics.py
  - id: openwiki-source-4fe6ccee48c3dff5a3831de8
    resource: repo://apps/api/tests/streaming/test_record_agent_run.py
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
---

# Observability, turn metrics and cost

Every agent turn, on both the JSON `/agent/chat` and the SSE `/agent/stream` endpoint, produces one `agent_runs` row plus a list of `agent_run_steps` rows. Collection is deliberately **best-effort and content-free**: nothing on the reply path may raise because a metric failed to populate, and no message text, tool arguments or PII are ever written to these tables. Optional Langfuse tracing sits alongside as a separate, off-by-default channel.

## The per-turn metrics handler

`TurnMetricsHandler` (`apps/api/app/agents/metrics.py`) is a LangChain `BaseCallbackHandler` created once per turn by the agent router and attached to the graph invocation's `callbacks`. It is thread-safe (tools run in worker threads) and runs inline so sync hooks stay on the event-loop thread for async runs. Every hook swallows its own exceptions, so a broken hook leaves counters intact (`tests/agents/test_turn_metrics.py::test_hook_exception_leaves_counters_intact`).

It collects three things:

- **LLM usage per model.** `on_chat_model_start` records the model name from the run metadata; `on_llm_end` reads `usage_metadata` from the resulting `AIMessage`, merges it per model with `add_usage` (including `cache_read` tokens as `cached_tokens`), and counts calls. A call without a model name or usage is counted but not aggregated; the name from the start hook is used when the end message lacks one. `on_llm_error` increments `llm_errors`.
- **Node timings.** `on_chain_start` opens a timing for the `langgraph_node` in the metadata, keyed by `_node_key`: inside a sub-graph (a `|` in `checkpoint_ns`) the key becomes `<ns_root>/<node>` so parallel `Send` workers and same-named inner nodes do not collide. Nested runs sharing one namespace are de-duplicated, and the namespace is released when the outermost run closes so a `RetryPolicy` re-execution is timed again.
- **Steps.** Each LLM call, tool call and node span becomes a step dict with `seq` in start order (so a node span sorts above the children it brackets), `offset_ms` from turn creation, `ms`, `status`, and attribution fields (`node`, `ns`, `model`, `tool_name`, `specialist`). Steps are capped at `MAX_STEPS_PER_TURN` (200); beyond that they are counted in `steps_dropped` while totals stay exact. `error_type` is always `type(exc).__name__`, never `str(exc)`, because an exception string can quote user input; `meta` only accepts a scalar allowlist. The handler emits `finish_reason`, and the repository re-applies its own allowlist, which also admits the internal run ids and verdicts `resumed_from` and `rubric_status` used by research runs. Tool inputs and outputs and chain outputs are never read.

The `specialist` field comes from run-config metadata that the synthesis worker merges in before invoking a specialist; it is the only channel that reaches the callbacks from inside a `Send` worker (see [Agent graph and supervisor routing](graph-and-supervisor.md)).

`close(started)` sets wall-clock `latency_ms` from an owner-held start time; `close_if_open()` falls back to the handler's creation time and sweeps any still-open steps to status `unfinished`, so a failed or cancelled turn still records real latency instead of dropping out of the rollups. `snapshot()` returns the full server-side dict (`by_model`, `by_node`, totals, `cost_usd`); `public()` returns the client-facing subset without the per-node breakdown, and a test pins that key set exactly.

## Recording a run

The router mints the run id up front and inserts a `running` row through `AgentRunRepository.start` with user, conversation, thread id, trip id, `channel` (`chat` or `stream`) and `kind` (`turn` or `resume`). The same id is passed as the LangChain root `run_id` so traces and metrics correlate.

Trip-research runs reuse the same tables. `ResearchService` inserts the row with `channel` and `kind` both set to `research`, and uses the per-trip dossier thread `research:{user_id}:{trip_id}` as both the thread id and the conversation id. The background runner attaches its own `TurnMetricsHandler` and finalizes the row on an isolated session factory. A failure is recorded as a terminal `node` step carrying `error_type`, because the run row has no error column. The grader's verdict is recorded as a terminal `rubric` step whose `meta.rubric_status` the status API maps to `passed` or `needs_review`. A resumed run stamps `resumed_from` on its first step. See [Trip-research deep agent](trip-research-deep-agent.md).

Finalization for chat turns differs by channel but stores identical rows:

- **JSON endpoint.** `_finalize` closes the metrics, prices them, builds the `usage` block returned to the client, and calls `finish` with the terminal status (`completed`, `interrupted` or `failed`) and the graph's baked-in `prompt_versions`. Steps are written on the request session **before** its commit, because a background task writing against a flushed-but-uncommitted row deadlocked. The post-graph writes are committed explicitly, otherwise the row would stay `running` forever.
- **SSE endpoint.** `record_agent_run` (`app/streaming/agent_run.py`) is an async pass-through that yields every event unchanged and, in a `finally`, derives the status from what it saw (`interrupt` event → `interrupted`; `error` event, exception or client cancellation → `failed`; else `completed`), reads `current_flow` from the `done` payload, closes and prices the metrics if the success path never did, and calls `finish` plus `add_steps` on an isolated session factory. A `CancelledError` marks the row failed and is re-raised. `tests/streaming/test_record_agent_run.py` covers the three statuses.

`finish` ignores unknown metric keys and logs-and-skips a missing row; `add_steps` has no existence check and would insert orphans rather than raise. Background memory extraction later adds its own LLM calls, tokens and milliseconds to the same row via `add_background` (see [Conversation memory and persistence](memory-and-persistence.md)).

## Tables

`agent_runs` holds per-turn identity (`user_id`, `conversation_id`, `thread_id`, `trip_id`, `channel`, `kind`), lifecycle (`status`, `current_flow`, `started_at`, `finished_at`, `latency_ms`), counters (`llm_calls`, `llm_errors`, `input_tokens`, `output_tokens`, `cached_tokens`, `cost_usd`), JSON breakdowns (`by_model`, `by_node`), the background extraction counters and the `prompt_versions` snapshot. `agent_run_steps` holds one row per step in `seq` order with the attribution fields, token counts, `prompts` JSON, `cost_usd`, `offset_ms`, `ms`, `status`, `error_type`, `tool_name` and the allowlisted `meta`. Assistant `messages` rows link back through `agent_run_id`, which is what lets the feedback endpoint refuse to rate a failed run.

## Cost and prompt attribution

`enrich_steps` (`app/agents/prompt_map.py`) is shared by both persistence sites. For each step it attaches `prompts`, a list of `{name, version}` pointers resolved from `PROMPTS_FOR_NODE` using the node key (a worker's `assistant` step is re-keyed to `<specialist>/assistant` so it attributes to the specialist's prompts), and for LLM steps a `cost_usd` computed by `estimate_cost` from the static price table in `app/core/pricing.py`. The versions come from the `prompt_versions` snapshot taken when the graph was compiled, not from the current `active.yaml`, so a prompt bump after startup does not misattribute in-flight runs (see [Prompt registry and versioning](prompt-registry.md)). `estimate_cost` returns `None` rather than `0.0` for unknown models.

The dashboard reads these tables for 24-hour and 7-day totals, the recent-runs list and a per-run step view; see [Admin API and server-rendered dashboard](../operations/admin-and-dashboard.md).

## Langfuse tracing

`app/agents/observability.py` builds a Langfuse `CallbackHandler` only when `LANGFUSE_ENABLED` is true; the client and handler are built once per unique settings combination through `functools.cache`, and any construction error logs and degrades to no tracing. `callbacks()` returns `[handler]` or `[]`, and `trace_metadata` tags each run with `langfuse_user_id`, `langfuse_session_id` (the trip id or `none`) and a `travel-agent` tag so traces group by user and trip. When disabled, no client is constructed at all (`tests/agents/test_observability.py`).

## Prompt-cache reporting scripts

Two operational scripts in `apps/api/scripts/` read the step rows:

- `cache_hit_report.py` aggregates `llm` steps into a per node-and-model cache hit-rate table over a window (`--since 7d`), and `--min-ratio` turns it into a CI-style gate on the **overall** ratio only, because nodes below OpenAI's 1,024-token caching floor legitimately report 0%. Exit code 3 means nothing was measured and fails closed under the gate.
- `probe_cache_retention.py` is a two-phase A/B probe (`--seed`, then `--check` after an idle gap) with a `24h` retention arm and an `in_memory` control, because a single arm cannot attribute a hit to the retention setting; it stamps an `attempted_at` marker before checking because a cache read refreshes the idle timer and a re-check would otherwise appear to succeed forever.
