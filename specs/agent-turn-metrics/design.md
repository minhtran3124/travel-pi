# agent-turn-metrics — Design

Status: reviewed 2026-09-03 (spec-document-reviewer: approved after one consistency fix; forks
resolved by the human at intake)
Lane: high-risk · Source: docs/reviews/2026-09-02-deep-review.md §3.B item 6

## 1. Purpose

Record, for every agent turn, how many LLM calls it made, how many tokens each model consumed
(input / output / cached), what that costs in USD, how long the turn and each graph node took —
and keep that as a queryable row per turn so the eval harness, the operator dashboard and the
follow-up decisions in the review (reflection keep/replace, model per tier, prompt caching, free
tier limits) have a baseline. Today nothing records any of this, and no OpenAI call even returns
`usage_metadata` (see SUMMARY.md "Intake findings").

Success looks like: after one `/agent/chat` or `/agent/stream` turn with the real provider, one
`agent_runs` row exists with non-zero tokens, a cost, a latency and a per-node breakdown; the
client sees the same totals in the reply; the dashboard lists the row.

## 2. Constraints

- Works identically for `/agent/chat` (`graph.ainvoke`) and `/agent/stream` (`graph.astream`
  with `subgraphs=True`), for HITL resume turns, and for the FakeLLM offline suite.
- Never affects the reply: metric collection and persistence are best-effort (log and
  continue), same posture as `persist_assistant_turn` and Langfuse.
- Additive schema only; SQLite (create_all) and Postgres (Alembic) both supported.
- Table shape stays compatible with `specs/user-feedback-v1/DESIGN.md` §3.1 so feedback-v1 can
  attach `agent_run_id` later instead of creating a second run entity.
- No new dependency. No PII in the row (no message text, no tool args).
- Out of scope (own specs): prompt prefix stabilisation / cache-hit optimisation, merging
  supervisor + slot extraction, feedback attachment, Langfuse cost views, OTel semconv.

## 3. Approaches considered

| | Approach | Verdict |
|---|---|---|
| **A** | **LangChain callback handler attached in `_config` (next to the Langfuse handler).** Sees every LLM call and every graph node, in both `ainvoke` and `astream`, including sub-graphs and `Send` workers, without touching node code. | **Chosen.** Same attachment point Langfuse already uses; one code path for both endpoints. |
| B | Parse the `"messages"` stream chunks in `streaming/mapper.py` and sum `usage_metadata`. | Rejected: `/agent/chat` does not stream; no latency per node; duplicates work already done by `langchain_core.callbacks.UsageMetadataCallbackHandler`. |
| C | Wrap each graph node (decorator) to time it and read usage from returned messages. | Rejected: touches 14 nodes + 5 sub-agent builders; misses structured-output calls that do not return messages. |

Within A, token accounting reuses the stdlib handler pattern (`UsageMetadataCallbackHandler`,
langchain-core ≥ 0.3.49, present in 1.4.8) rather than the class itself, because we also need
per-call latency, call count, and node timing in the same object.

## 4. Architecture

```
router (/agent/chat | /agent/stream)
  │  1. run_id = uuid4() (router-minted, before any DB work — feedback-v1 §3.1 "minted before graph invocation")
  │     AgentRunRepository.start(run_id, ...)  → agent_runs row (status=running); insert failure is logged, run_id kept
  │  2. handler = TurnMetricsHandler()  → cfg["callbacks"] = langfuse + [handler]; cfg["run_id"]=UUID(run_id)
  │  3. graph.ainvoke / stream_agent_events(..., metrics=handler)
  │  4. finish: repo.finish(id, status, handler.snapshot())      (chat: inline; stream: pass-through wrapper)
  │  5. reply carries snapshot.public()  → ChatResponse.usage / done.usage
  └─ background memory extraction: extract_memories(..., callbacks=[handler]) then repo.add_background(id, ...)
```

### 4.1 `TurnMetricsHandler` — `app/agents/metrics.py` (new)

`BaseCallbackHandler` subclass, one instance per turn, `run_inline = True`, thread-safe (tools run
in worker threads), never raises (every hook body wrapped; `raise_error=False`).

| Hook | What it records |
|---|---|
| `on_chat_model_start` | start time keyed by `run_id`; model name from `metadata["ls_model_name"]` (fallback `serialized` kwargs / `invocation_params["model"]`). |
| `on_llm_end` | `llm_calls += 1`; per-call latency; `usage_metadata` from `generations[0][0].message` (`AIMessage.usage_metadata`; `input_token_details.cache_read` → cached); aggregated per model with `add_usage`. Model name prefers `response_metadata["model_name"]`. |
| `on_llm_error` | `llm_errors += 1`; latency still closed. |
| `on_chain_start` / `on_chain_end` / `on_chain_error` | only when `metadata` carries `langgraph_node` **and** its `langgraph_checkpoint_ns` has not been seen yet in this turn (LangGraph task metadata is inherited by every nested run — tool calls, inner LLM runs — so only the first `run_id` per checkpoint namespace is the node task itself; later runs with the same namespace are ignored). Wall-clock per node keyed `"<ns_root>/<node>"` for sub-graph nodes so parallel `Send` workers do not collide. Accumulates across task executions (ReAct loops, reflection revisions each get a new namespace). |

`snapshot()` returns a plain dict:

```
{
  "llm_calls": 7, "llm_errors": 0, "latency_ms": 8421,            # latency_ms set by the owner (turn wall-clock)
  "input_tokens": 12034, "output_tokens": 812, "cached_tokens": 0, "total_tokens": 12846,
  "by_model": {"gpt-5-mini": {"input_tokens":..., "output_tokens":..., "cached_tokens":..., "calls": 5}, ...},
  "by_node":  {"supervisor": {"ms": 910, "runs": 1}, "planner": {"ms": 6200, "runs": 1}, "planner/tools": {...}, "reflection": {...}},
  "cost_usd": 0.0041 | None
}
```

`public()` returns the client-facing subset: `input_tokens, output_tokens, cached_tokens,
total_tokens, llm_calls, latency_ms, cost_usd, models: [..]` (no per-node breakdown — that stays
server-side to keep the public contract small).

### 4.2 Pricing — `app/core/pricing.py` (new)

Static table `MODEL_PRICES_USD_PER_1M: dict[str, ModelPrice(input, output, cached_input)]`
covering the models in the provider catalogue (`LLM_PROVIDERS[*].models`) plus the two defaults
(`gpt-5`, `gpt-5-mini`). Lookup normalises snapshot suffixes (`gpt-5-2026-…` → `gpt-5`).
`estimate_cost(by_model) -> float | None` = Σ ((input − cached)·p_in + cached·p_cached +
output·p_out) / 1e6; returns **None if any model is unknown** (a partial number is worse than
none). Prices are data, not logic: verified against the provider pricing page at implementation
time and dated in the file header; unit test pins the formula, not the numbers.

### 4.3 `stream_usage=True` — `app/clients/llm.py`

`_build_chat_model` adds `stream_usage=True` **only when `profile.sdk == "openai"`**: the
field is OpenAI-specific (ChatAnthropic 1.4.7 already declares `stream_usage: bool = True`;
ChatGoogleGenerativeAI is not installed locally and unverified), so the kwarg is scoped to the
one SDK that needs it rather than sprayed across profiles. With `streaming=True` this is what makes both `invoke` and `stream` return
`usage_metadata` (langchain-openai 0.3.34 defaults it to False).

### 4.4 Data model — `app/db/models/agent_run.py` + Alembic (additive)

Table `agent_runs` (`UUIDBase`: id, created_at, updated_at). Columns follow feedback-v1 §3.1
where they overlap; metrics columns are new:

| Column | Type | Notes |
|---|---|---|
| `user_id` | str, idx, not null | effective owner |
| `conversation_id` | str, idx, not null | |
| `thread_id` | str, not null | LangGraph thread key |
| `trip_id` | str, null | |
| `channel` | str, not null | `chat` / `stream` |
| `kind` | str, not null | `turn` / `resume` (HITL) |
| `status` | str, idx, not null | `running` → `completed` / `interrupted` / `failed`; a row left `running` is *abandoned* (client disconnected) |
| `current_flow` | str, null | final flow |
| `started_at`, `finished_at` | ISO str / null | |
| `latency_ms` | int, null | turn wall-clock incl. stream drain, excl. background |
| `llm_calls`, `llm_errors` | int, default 0 | |
| `input_tokens`, `output_tokens`, `cached_tokens` | int, default 0 | totals |
| `cost_usd` | float, null | None when a model has no price |
| `by_model` | JSON, null | snapshot `by_model` |
| `by_node` | JSON, null | snapshot `by_node` |
| `background_llm_calls`, `background_tokens`, `background_ms` | int, default 0 | memory extraction, written after the response |
| `assistant_message_id`, `trace_id`, `prompt_versions`, `model_config`, `execution_summary`, `app_release` | — | **not created now**; feedback-v1 adds them in its own additive revision |

Revision `<new>_add_agent_runs` (`down_revision = "c7f1a9d4e6b2"`): `create_table` +
indexes; `downgrade` drops the table. No data movement.

Repository `app/repositories/agent_run.py` (`AgentRunRepository`, same session-or-factory
constructor as `ConversationRepository`): `start(id, *, user_id, conversation_id, thread_id,
trip_id, channel, kind, started_at) -> None` (the id is router-minted, never generated here),
`finish(id, *, status, current_flow, finished_at, metrics)`, `add_background(id, *, llm_calls, tokens, ms)`, `list_recent(limit)`,
`totals(since)`.

### 4.5 Wiring — `app/routers/agent.py`

- `_config(...)` gains `metrics: TurnMetricsHandler` and `run_id: str`: `"callbacks":
  callbacks() + [metrics]`, `"run_id": UUID(run_id)` (the LangChain root run id only; langfuse 4.12.0 derives its trace
  id from `trace_context` / OTel context, never from `run_id`, so no correlation is claimed),
  `"metadata"` unchanged.
- **chat:** row started right before `graph.ainvoke` (committed with the existing
  `session.commit()`); after the run, `finish` with status from the outcome
  (exception → `failed`, `__interrupt__` → `interrupted`, else `completed`); `ChatResponse.usage
  = metrics.public()`. The `failed` branch still finishes the row and returns
  `usage` (whatever was collected).
- **stream:** row started before `session.commit()`; new pass-through
  `record_agent_run(events_iter, *, run_id, metrics, session_factory, started)` in
  `app/streaming/agent_run.py` (sibling of `persist_assistant_turn`): passes events through,
  notes `interrupt` / `error` events for the status, reads `current_flow` from the `done`
  event payload (the only place a pass-through can see it), and on exhaustion (or `finally` on
  cancel → `failed`) writes `finish` via the isolated factory. Nesting order, innermost first:
  `persist_assistant_turn(record_agent_run(stream_agent_events(...)))` — the run row closes the
  moment the graph stream ends, and the reply persistence stays the outermost stage as today.
  `stream_agent_events` gains `metrics: TurnMetricsHandler | None` and passes
  `usage=metrics.public()` into `events.done(...)` so the client sees totals.
- **background extraction:** `run_memory_extraction[_from_stream]` gain `run_id` +
  `session_factory` + `callbacks`; `extract_memories(messages, llm, callbacks=...)` forwards to
  `llm.invoke(msgs, config={"callbacks": callbacks})`; afterwards `add_background`. Uses a
  fresh `TurnMetricsHandler` so background numbers are separate columns.

### 4.6 Contract — `app/schemas/agent.py`, `app/streaming/events.py`

New `TurnUsage(AppBaseModel)`: `input_tokens, output_tokens, cached_tokens, total_tokens: int`,
`llm_calls: int`, `latency_ms: int | None`, `cost_usd: float | None`, `models: list[str]`.
`ChatResponse.usage: TurnUsage | None = None` (None on the fallback path only if collection
itself failed). `done` event payload gains `"usage": {...}` (same shape) — additive; the web
client ignores unknown fields (verify `apps/web` SSE parser tolerates it; no FE change).

### 4.7 Dashboard — `app/routers/dashboard.py` + `templates/agent_runs.html`

`GET /dashboard/agent-runs` (behind the existing `require_dashboard_access` guard, hidden in
prod like the rest): last 100 runs (time, user, channel/kind, status, flow, calls, tokens
in/out/cached, cost, latency) + a totals strip for the last 24 h / 7 d (turns, tokens, cost,
p50 / p95 latency computed in Python — no SQL percentile). Read-only. Link from `base.html` nav.

## 5. Error behaviour

- Handler hook raises → caught inside the hook, logged once at DEBUG, counters unchanged.
- `usage_metadata` missing on a message (provider off, FakeLLM item built without it) → call
  counted, tokens unchanged; snapshot still valid.
- Row insert fails (DB down) → logged at ERROR, `run_id` still minted (UUID) so the graph run
  proceeds with the same config; `finish` is skipped when `start` failed.
- `finish` fails → logged at ERROR; reply already sent / unaffected.
- Client disconnects mid-stream → `record_agent_run`'s `finally` marks `failed` (`cancelled`
  in `by_node["_reason"]` is *not* used; a plain status is enough); if even that fails the row
  stays `running` = abandoned, visible on the dashboard.
- Unknown model in pricing → `cost_usd = None`, tokens still recorded.
- Recursion-limit / LLM outage → the router's existing fallback path runs; row `failed` with
  whatever was collected.

## 6. Tests (FakeLLM, offline)

- `FakeLLM._next` attaches `usage_metadata={"input_tokens": 10, "output_tokens": 5,
  "total_tokens": 15}` and `response_metadata={"model_name": "fake-llm"}` to every generated
  `AIMessage` (unless the scripted item already carries usage). Existing exact-equality
  assertions on FakeLLM messages, if any, are updated.
- `tests/agents/test_turn_metrics.py`: handler unit tests — usage aggregation per model,
  cached tokens, llm_error counting, node timing keyed by ns root, hook exceptions swallowed,
  `public()` shape.
- `tests/core/test_pricing.py`: formula, cached discount, unknown model → None, snapshot suffix
  normalisation.
- `tests/clients/test_llm.py`: OpenAI profile model has `stream_usage=True`; anthropic profile
  does not receive the kwarg.
- `tests/api/agent/test_agent_runs.py`: `/agent/chat` → `usage.llm_calls ≥ 1` (loose on purpose:
  `FakeLLM.with_structured_output` returns a `RunnableLambda`, so supervisor/reflection
  structured calls never fire `on_llm_end` offline — only `_generate` calls count; do not
  "fix" this),
  `input_tokens > 0`, row `completed` with `by_node` containing `supervisor`; failed run → row
  `failed`; HITL interrupt → `interrupted`, `kind="resume"` on the resume turn.
- `tests/api/agent/test_stream_events.py`: `done.usage` present; exact-shape lists updated
  (`start … done` names unchanged; payload gains `usage`).
- `tests/streaming/test_record_agent_run.py`: pass-through + status from events + cancel path.
- `tests/test_db_models.py`: `agent_runs` in the registered-tables set + column set.
- `tests/api/agent_config/test_agent_runs_dashboard.py` (next to the existing dashboard tests
  `test_agent_config_dashboard.py` / `test_dashboard_auth.py`; there is no `tests/api/dashboard/`):
  200 with the guard, 404 in prod.
- Alembic: `upgrade head` / `downgrade -1` round trip on a temp SQLite DB.

## 7. Open assumptions (documented defaults, not asked)

- A HITL resume is its own run row (`kind="resume"`), not a continuation of the paused row.
- Background extraction counts in separate `background_*` columns rather than in the turn totals
  the client sees, because the client already has its reply when those calls happen.
- Latency for the stream channel is measured from handler creation to stream exhaustion
  (includes network drain); that is what the user experiences.
- `by_node` uses `"<root>/<node>"` only for nodes inside a sub-graph namespace; root nodes keep
  their bare name.
