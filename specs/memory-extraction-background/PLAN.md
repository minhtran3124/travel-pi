---
slug: memory-extraction-background
status: proposed
owner: Minh Tran
created: 2026-07-04
---

# Memory Extraction as a Post-Response Background Task

## 1. Motivation

The `extract_memory` graph node adds one synchronous LLM call to the critical path
of every non-FAST turn. It runs *after* the user's answer is already known
(reflection → `extract_memory` → `END`), yet the client cannot see `done` until
that extra call returns. Moving extraction out of the LangGraph graph and running
it as a FastAPI background task — after the response is sent, on the existing
in-process stack — removes that latency from every turn while preserving the exact
same writes to the long-term store.

This deliberately does NOT adopt LangChain Agent Protocol / deep-agents (rejected
as over-engineering). The node body moves, almost verbatim, into a shared runner
that both endpoints schedule.

## 2. Non-goals

- No change to *what* is extracted (`extract_memories` + `upsert_*` are untouched).
- No new task queue / broker / worker process — FastAPI `BackgroundTasks` +
  Starlette `BackgroundTask` only.
- No change to the LangGraph checkpointer/store lifecycle or `resolve_travel_graph`
  rebuild semantics.
- `extract_memory` stays a configurable LLM node in `agent_config` and in
  `FAST_AGENTS` (its model is still resolved; only its *execution site* moves).

## 3. Success Criteria

- The compiled graph contains no `extract_memory` node; `reflection` terminates at
  `END`. Turn latency no longer includes the extraction LLM call.
- `/chat` and `/stream` schedule extraction **after** the reply is produced, and
  **skip** it whenever a plan-approval interrupt is pending.
- Extraction writes the same preferences/instructions/episodes to the
  process-lifetime store as before; all failures are still swallowed.
- Tests stay hermetic: the extraction LLM + store are injected through the
  existing `build_graph` / `get_travel_graph` seam — no new network calls.
- `make test` is green.

## 4. Tasks

### Task 1.1 — Extraction runner service (new module + unit tests)

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/memory/extraction_runner.py, apps/api/tests/memory/test_extraction_runner.py</files>
  <action>Create run_memory_extraction(*, messages, user_id, trip_id, plan_approved, allow_memory_write, store, llm) -> None as a plain sync function holding the exact body of make_extract_memory_node.extract_memory (guard clauses: return early when not allow_memory_write, or no user_id, or store is None; then extract_memories(messages, llm) + upsert_preference/instruction/episode with the plan_approved→outcome="approved" logic). Wrap the write block in try/except Exception: logger.exception (best-effort, never raises). It touches ONLY the LangGraph store (not any ORM Session), so the isolated-session guideline is satisfied by construction. Add unit tests using FakeLLM + InMemoryStore that assert prefs/instructions/episodes are written, that allow_memory_write=False writes nothing, that empty JSON writes nothing, and that a raising llm is swallowed — porting the store-assertion cases from tests/agents/test_memory_extraction.py.</action>
  <verify>pytest tests/memory/test_extraction_runner.py -x</verify>
  <done>Runner writes to the store for happy paths and is a silent no-op on gates/errors; unit tests pass.</done>
</task>
```

### Task 2.1 — Remove node, rewire graph, retarget reflection, expose extract LLM

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/agents/nodes.py, apps/api/app/agents/graph.py, apps/api/tests/agents/test_depth_toggles.py, apps/api/tests/agents/test_supervisor.py, apps/api/tests/agents/test_memory_extraction.py</files>
  <action>In nodes.py: delete make_extract_memory_node and its now-unused imports (extract_memories, upsert_* ); in make_reflection_node retarget all three terminal emissions to END (L128 goto=END, L138 target = state.get("current_flow") or END, L154 goto=END). In graph.py: import END (already imported); remove the make_extract_memory_node import and the add_node("extract_memory", ...) + add_edge("extract_memory", END); change reflection destinations to (*SUBAGENTS, END). Keep computing pick("extract_memory") but attach it to the compiled graph before returning: compiled = builder.compile(...); compiled.extract_memory_llm = pick("extract_memory"); return compiled — this reuses the SINGLE existing injection seam (build_graph llm=/fast_llm= + get_travel_graph override) so the runner's LLM is the injected fake in tests and get_agent_llm("extract_memory") in prod; the store is already exposed as compiled.store. Update test_depth_toggles.py and test_supervisor.py asserts from goto=="extract_memory" to goto==END (import END from langgraph.graph). Delete tests/agents/test_memory_extraction.py — its graph-drives-extraction assertions are superseded by test_extraction_runner.py (Task 1.1) and the router tests (Waves 3–4).</action>
  <verify>pytest tests/agents/test_depth_toggles.py tests/agents/test_supervisor.py tests/agents/test_graph.py tests/agents/test_hitl_plan.py -x</verify>
  <done>Graph has no extract_memory node; reflection ends at END; compiled graph exposes extract_memory_llm + store; reflection/graph/HITL tests pass.</done>
</task>
```

### Task 3.1 — /chat schedules extraction as a BackgroundTask

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/routers/agent.py, apps/api/tests/api/agent/test_agent_chat.py</files>
  <action>Add background: BackgroundTasks to agent_chat. After computing interrupt_pending and BEFORE returning (only on the success path, never in the except fallback), schedule extraction when NOT interrupt_pending: background.add_task(run_memory_extraction, messages=result["messages"], user_id=result.get("user_id"), trip_id=result.get("trip_id"), plan_approved=result.get("plan_approved", False), allow_memory_write=ctx.allow_memory_write, store=graph.store, llm=graph.extract_memory_llm). The runner re-checks its own gates, so this is double-safe. Add tests: (a) a non-FAST /chat turn writes the scripted preference to the injected store after the response; (b) a booking turn that returns interrupt_pending schedules NO extraction (store stays empty). Reuse _make_app's fake fast LLM as the extraction LLM (it is graph.extract_memory_llm) and assert via search_preferences on the graph's store.</action>
  <verify>pytest tests/api/agent/test_agent_chat.py -x</verify>
  <done>/chat runs extraction post-response on normal turns and skips it on interrupt; chat tests pass.</done>
</task>
```

### Task 4.1 — /stream schedules extraction after the stream drains

```xml
<task id="4.1" wave="4">
  <files>apps/api/app/routers/agent.py, apps/api/app/streaming/mapper.py, apps/api/app/core/streaming.py, apps/api/tests/api/agent/test_stream_persistence.py</files>
  <action>In mapper.stream_agent_events add an optional final_state_sink: dict | None = None param; at the existing post-drain state fetch (state = await graph.aget_state(cfg)) also populate the sink when provided: sink["values"] = state.values if state else {}; sink["interrupt_pending"] = bool(state.interrupts). In core/streaming.sse_response add an optional background: BackgroundTask | None = None param and pass it through to StreamingResponse(..., background=background). In routers/agent.agent_stream: create sink: dict = {}; pass final_state_sink=sink into stream_agent_events; build a Starlette BackgroundTask(run_memory_extraction_from_stream, sink=sink, ctx=ctx, store=graph.store, llm=graph.extract_memory_llm) and pass it as sse_response(..., background=...). Add a thin adapter run_memory_extraction_from_stream in extraction_runner.py that reads values/interrupt_pending from the sink, returns early if interrupt_pending or sink empty, else calls run_memory_extraction with the sink's user_id/trip_id/plan_approved/messages + ctx.allow_memory_write. Starlette runs the StreamingResponse background AFTER the body completes, so extraction is off the reply path. Add tests: a non-resume /stream turn writes the scripted preference to the graph's store after the SSE completes; a booking /stream turn that emits an interrupt event writes nothing.</action>
  <verify>pytest tests/api/agent/test_stream_persistence.py -x</verify>
  <done>/stream runs extraction via the response background after the stream drains and skips on interrupt; stream-persistence tests pass.</done>
</task>
```

> Note: Task 4.1 adds a second helper to `extraction_runner.py`, first created in
> Task 1.1 — a cross-wave edit of the same file (allowed; only *intra-wave* overlap
> is forbidden). If preferred, the sink-adapter can instead live inline in
> `agent.py`; the plan keeps it in the runner module for cohesion.

### Task 5.1 — Final consolidation, constant review, full-suite gate

```xml
<task id="5.1" wave="5">
  <files>apps/api/tests/agents/test_procedural_injection.py</files>
  <action>Update the stale "reflection + extract_memory will use fast" comment (extraction no longer runs in-graph); the extra scripted extractor JSON in the fast FakeLLM is now unused but harmless (FakeLLM cycles) — either drop it or leave with a corrected comment. Confirm (no code change) that extract_memory REMAINS in FAST_AGENTS (constants.py) and in agent_config.py: its LLM is still resolved via get_agent_llm("extract_memory"), so removing it from FAST_AGENTS would silently promote it to the pricier main model. No other set references it beyond FAST_AGENTS, AGENT_CONFIG_GROUPS, and the dashboard emoji.</action>
  <verify>make test</verify>
  <done>Full SQLite suite green; no stale extract_memory graph references remain.</done>
</task>
```

## 5. Risks

- **Interrupt-skip correctness.** Both endpoints must skip extraction while a
  plan-approval interrupt is pending (graph paused at `plan`, extraction never
  reached today). `/chat` gates on its computed `interrupt_pending`; `/stream`
  gates on `sink["interrupt_pending"]` derived from `graph.aget_state(cfg).interrupts`.
  On the *resumed* (approved) turn the interrupt is cleared, so extraction runs
  once, with `plan_approved=True` — matching prior behavior. Tests cover both the
  interrupt turn (skip) and a normal turn (run).
- **Streaming final-state retrieval.** The final `messages`/`user_id`/`trip_id`/
  `plan_approved` are only known after the stream drains. They are captured into a
  mutable `sink` at the mapper's existing `aget_state` point and read by the
  Starlette response-background task after the body completes. If the stream
  crashes before that point the sink stays empty and extraction is skipped.
- **Test hermeticity.** Resolved by attaching `extract_memory_llm` to the compiled
  graph and reading the store off `graph.store`, so the existing `build_graph`/
  `get_travel_graph` override injects the fake fast LLM + `InMemoryStore` with zero
  new seams. (Rejected: stashing on `app.state`, because `TestClient` runs
  `lifespan`, which would populate a real, network-capable `get_agent_llm` llm that
  every router test would then have to override.)
- **Background error swallowing preserved.** `run_memory_extraction` keeps the
  node's `try/except Exception: logger.exception` around the write block, so a
  failed extraction never affects the (already-sent) response. FastAPI/Starlette
  background failures are logged, not surfaced.
- **Store concurrency (minor).** The runner writes to the process-lifetime store
  from a threadpool/background context; this mirrors the checkpointer's existing
  cross-request use. Assumed thread-safe; flagged for validation under Postgres.
- **Green-between-waves.** Removing the node (Wave 2) breaks any test that assumed
  in-graph extraction, so the reflection-goto asserts and the obsolete
  `test_memory_extraction.py` are handled *inside* Wave 2 (not deferred to Wave 5),
  keeping the suite green after every wave.

## 6. Status Log

- 2026-07-04 — Plan drafted (status: proposed).
- 2026-07-04 — Shipped on `feat/memory-extraction-background` (status: shipped). Commits:
  W1 `7cd6471` runner + tests · W2 `104b406` remove node / reflection→END + expose `extract_memory_llm` ·
  W3 `170dbeb` /chat BackgroundTask · W4 `8dee139` /stream response-background · W5 comment cleanup.
  Compiled-graph attribute risk closed (plain attr works — `CompiledStateGraph`/`Pregel` are plain classes).
  Full suite: **1237 passed** (`make test`, run with `.env` aside per env-openai-key gotcha).
