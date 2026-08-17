---
slug: gh-117-agent-synthesis-send
status: shipped
owner: minh.tran
created: 2026-08-13
---

# GH-117 — Agent synthesis via LangGraph `Send` / map-reduce

## Design decision — hybrid routing

Use LangGraph's `Send` API to run sub-agents in parallel and a `synthesize` node to
produce one final answer, **but preserve the existing static sub-agent path for
single-intent turns.**

Why hybrid:
- Single-intent turns are the common case and work well today (streaming tokens,
  bounded reflection, no duplication). Re-architecting them would be a large public-
  contract change for no user-visible benefit.
- Multi-intent turns are the only case with duplication. Routing them through a
  dedicated parallel worker path fixes the bug without touching the happy path.

Path B (serial synthesis inside the existing graph) was rejected by the user after
a side-by-side comparison. Path A is the chosen direction.

## 1. Motivation

Issue #117: when the supervisor queues multiple sub-agents for one user message,
each sub-agent regenerates the whole turn answer, causing duplicate content in the
final REST reply and duplicate tokens in the SSE stream.

Today's workaround (`superseded_message_ids` + SSE token suppression) only keeps the
last sub-agent's answer. The user gets a single non-duplicated message, but it is
only the *last* specialist's regenerated answer — not a true synthesis of all the
specialists' work.

Goal: run all queued specialists, gather their findings, and synthesize one
user-facing answer.

## 2. Non-goals

- **Do not change single-intent behavior.** The existing static sub-agent nodes,
  streaming, reflection, and tests stay unchanged for single-intent turns.
- **Do not add mid-turn replanning.** The supervisor still emits a fixed plan once
  per turn.
- **Do not parallelize booking.** Booking stays behind the HITL `plan_node` interrupt
  and is never queued as a follow-on task.
- **Do not remove the old workaround yet.** `superseded_message_ids` and SSE token
  suppression remain in place for any code path that still uses serial dispatch.
  They are only retired once the new path is proven and the old path is removed.

## 3. Success Criteria

- Multi-intent turns (e.g. "flights to Tokyo and things to do") run the relevant
  sub-agents in parallel via `Send`, then synthesize one answer.
- `/agent/chat` returns exactly one synthesized answer for multi-intent turns.
- `/agent/stream` emits one token stream for the synthesized answer; no duplicate
  prose from intermediate sub-agents.
- Single-intent turns remain byte-for-byte compatible with the merged workaround:
  all existing agent tests pass without modification.
- Tool panels and tool-result status events still stream during multi-intent turns.
- Reflection reviews the synthesized answer for multi-intent turns; if it asks for
  a revision, the graph re-synthesizes rather than re-running all workers.

## 4. Tasks

### Task 1.1 — Add task and result state schemas (wave 1)

- **Files:** `apps/api/app/agents/state.py`, `apps/api/app/agents/schemas.py` (create)
- **Action:** Define two Pydantic v2 models in the new `schemas.py`:
  - `AgentTask`: `agent: str`, `query: str`, `index: int`.
  - `TaskResult`: `agent: str`, `index: int`, `findings: str`, `panels: list[dict]`.
  Add two new keys to `TravelAgentState` in `state.py`:
  - `tasks: Annotated[list[AgentTask], _add_tasks]` — last-write-wins reducer
    (supervisor is the only writer per turn).
  - `task_results: Annotated[list[TaskResult], _append_results]` — append reducer
    for parallel worker writes.
  Keep `pending_flows` and `superseded_message_ids` untouched for the old path.
- **Verify:** `python -c "from app.agents.state import TravelAgentState; from app.agents.schemas import AgentTask, TaskResult; print('ok')"`
- **Done:** State module imports cleanly and the new keys survive a round-trip through
  `app.agents.state.TravelAgentState`.

### Task 1.2 — Refactor supervisor to emit tasks (wave 1)

- **Files:** `apps/api/app/agents/supervisor.py`
- **Action:** Change `make_supervisor` so the node returns `Command(update=...)`
  **without** `goto`. The update now writes:
  - `tasks`: a list of `AgentTask` objects. A single-intent turn gets one task; a
    multi-intent turn gets one task per specialist.
  - `language`, `trip_facts` as today.
  - For unknown intent or tier gating, emit the fallback `messages` and no `tasks`
    so the conditional edge routes to `END`.
  Keep the `plan` / `secondary_agent` parsing logic; map each queued step to an
  `AgentTask` with an incrementing `index`. The first task is the primary intent.
  Booking as a primary intent still produces a single `AgentTask(agent="booking")`.
- **Verify:** `DATABASE_URL=sqlite:///:memory: python -m pytest tests/agents/test_supervisor.py -q` (or the relevant supervisor unit tests if named differently)
- **Done:** Supervisor unit tests pass and the new `tasks` field appears in state.

### Task 1.3 — Add task routing conditional edge (wave 1)

- **Files:** `apps/api/app/agents/graph.py`, `apps/api/app/agents/nodes.py`
- **Action:** Add `route_tasks(state) -> str | list[Send]` in `nodes.py`:
  - If `state["tasks"]` is empty: return `END`.
  - If the first task is `booking`: return `"plan"` (HITL path).
  - If `len(tasks) == 1`: return `tasks[0].agent` (existing static sub-agent node).
  - If `len(tasks) > 1`: return `[Send("synthesis_worker", {"task": t}) for t in tasks]`.
  In `graph.py`, replace the old supervisor handoff with
  `builder.add_conditional_edges("supervisor", route_tasks)` and remove the
  `destinations=` list from the supervisor node. Keep all existing static sub-agent
  nodes and the `plan` node.
- **Verify:** `DATABASE_URL=sqlite:///:memory: python -m pytest tests/api/agent/test_agent_chat.py::test_chat_single_intent -x`
- **Done:** A single-intent turn still routes through the existing static sub-agent.

### Task 2.1 — Build synthesis worker subgraph (wave 2)

- **Files:** `apps/api/app/agents/subagents/_base.py`, `apps/api/app/agents/subagents/synthesis_worker.py` (create)
- **Action:** Create `synthesis_worker.py` with `build_synthesis_worker(resolve_model)`.
  The worker is a ReAct subgraph that:
  1. Reads `task` from the incoming state slice.
  2. Builds a system prompt that tells the specialist: "You are a background
     researcher. Use tools to gather facts. Return a concise, structured result
     with `findings` and optional `panels`. Do NOT write a user-facing answer."
  3. Runs the existing sub-agent tools for the requested `agent`.
  4. The final assistant call uses `with_structured_output(TaskResult)` so the
     output is a parseable `TaskResult` (set `index` and `agent` in code after parsing).
  Reuse the tool list and `resolve_model` from each existing sub-agent builder.
  Update `_base.py` to expose a helper `tools_for(agent)` if needed.
- **Verify:** `DATABASE_URL=sqlite:///:memory: python -m pytest tests/agents/test_synthesis_worker.py -q` (new unit test file)
- **Done:** A worker can be invoked with a task and returns a structured `TaskResult`.

### Task 2.2 — Add synthesize node (wave 2)

- **Files:** `apps/api/app/agents/nodes.py`
- **Action:** Add `make_synthesize_node(llm)` returning `synthesize(state) -> dict`.
  The node:
  1. Sorts `state["task_results"]` by `index`.
  2. Builds a system prompt: "You are the travel assistant. Combine the following
     specialist findings into one concise, helpful answer in the traveller's
     language. Do not repeat tool data; translate findings into guidance."
  3. Invokes the LLM with the sorted findings.
  4. Returns `{"messages": [AIMessage(content=answer)], "task_results": []}`
     (clears results so they do not leak into the next turn).
- **Verify:** `DATABASE_URL=sqlite:///:memory: python -m pytest tests/agents/test_synthesize.py -q` (new unit test file)
- **Done:** Synthesize node produces one AIMessage from multiple `TaskResult` objects.

### Task 2.3 — Wire worker + synthesize into graph (wave 2)

- **Files:** `apps/api/app/agents/graph.py`
- **Action:** Add the `synthesis_worker` subgraph node and a `synthesize` node.
  Add edges:
  - `synthesis_worker` → `synthesize` (each worker returns `Command(goto="synthesize")`).
  - `synthesize` → `reflection` (normal edge).
  Ensure `dispatch_next` still receives static sub-agent output for single-intent
  turns; the multi-intent path bypasses `dispatch_next` entirely.
- **Verify:** `DATABASE_URL=sqlite:///:memory: python -m pytest tests/api/agent/test_agent_chat.py -q`
- **Done:** Full agent test suite still passes (single-intent path unchanged; new
  multi-intent path compiles and runs).

### Task 2.4 — Adapt reflection for synthesized answers (wave 2)

- **Files:** `apps/api/app/agents/nodes.py`
- **Action:** Update `make_reflection_node` so that when `state["current_flow"]` is
  unset or set to a sentinel like `"synthesis"`, a REVISE verdict routes back to
  `"synthesize"` instead of a static sub-agent. On revise, append a
  `REFLECTION_REVISE_NOTE` system message and increment `revisions` as today.
- **Verify:** `DATABASE_URL=sqlite:///:memory: python -m pytest tests/api/agent/test_agent_chat.py::test_chat_reply_excludes_reflection_rejected_draft -x`
- **Done:** Reflection revision loop works for both static-sub-agent and synthesis paths.

### Task 3.1 — Update streaming mapper for synthesized path (wave 3)

- **Files:** `apps/api/app/streaming/mapper.py`
- **Action:** When a multi-intent turn is active (detect via `state["tasks"]` having
  length > 1 or via the `synthesize` namespace):
  - Suppress prose tokens from `synthesis_worker` subgraphs (they are structured,
    not user-facing).
  - Allow `synthesize` node prose tokens to stream normally.
  - Continue emitting `panel`, `tool_call`, and `tool_result` events from workers.
  Single-intent turns follow the existing logic unchanged.
- **Verify:** `DATABASE_URL=sqlite:///:memory: python -m pytest tests/api/agent/test_stream_events.py -q`
- **Done:** Existing stream tests pass; a new test verifies synthesized answer is
  streamed once for multi-intent turns.

### Task 3.2 — Update REST router final-answer assembly (wave 3)

- **Files:** `apps/api/app/routers/agent.py`
- **Action:** Ensure `/agent/chat` returns the last AIMessage content regardless of
  whether it came from a static sub-agent or the `synthesize` node. The current
  logic already extracts the last content-bearing message; confirm it handles the
  new path and does not accidentally concatenate worker findings.
- **Verify:** `DATABASE_URL=sqlite:///:memory: python -m pytest tests/api/agent/test_agent_chat.py::test_chat_multi_intent_turn_returns_last_subagent_answer -x`
- **Done:** REST endpoint returns the synthesized answer for the multi-intent test.

### Task 4.1 — Add multi-intent synthesis tests (wave 4)

- **Files:** `apps/api/tests/api/agent/test_agent_chat.py`, `apps/api/tests/api/agent/test_stream_events.py`
- **Action:** Replace or extend the existing #117 regression tests so they assert:
  - `/agent/chat` returns a synthesized answer containing key information from both
    specialists (e.g. flight result + sightseeing result) but not duplicated prose.
  - `/agent/stream` emits the synthesized answer tokens exactly once.
  Keep the old single-intent tests untouched.
- **Verify:** `DATABASE_URL=sqlite:///:memory: python -m pytest tests/api/agent/test_agent_chat.py tests/api/agent/test_stream_events.py -q`
- **Done:** New regression tests pass and old tests have no regressions.

### Task 4.2 — Run full agent regression and lint (wave 4)

- **Files:** all touched files
- **Action:** Run the full agent test suite, type checks, and lint.
- **Verify:**
  - `DATABASE_URL=sqlite:///:memory: python -m pytest tests/agents/ tests/api/agent/ -q`
  - `ruff check apps/api/app/agents apps/api/app/streaming apps/api/app/routers/agent.py`
  - `python -m pyright apps/api/app/agents` (if pyright is configured)
- **Done:** All checks pass.

## 5. Risks

- **Public contract change.** `/agent/chat` and `/agent/stream` answers for multi-intent
  turns will differ in wording from the merged workaround. Document this as an
  intentional improvement.
- **Structured output reliability.** Workers must return valid `TaskResult`. If the
  model fails, fall back to prose and log a warning.
- **Parallel tool-panel ordering.** Multiple workers may emit panels concurrently;
  the frontend already handles interleaved panels.
- **Recursion budget.** Parallel workers each run a ReAct loop inside one superstep.
  The ledger cap keeps total tool+LLM steps within the configured recursion limit.

## 6. Status Log

- 2026-08-13 — Plan proposed; Path A selected by user after comparison.
- 2026-08-13 — Implementation complete. Supervisor emits `tasks`, `route_tasks`
  dispatches parallel `synthesis_worker` subgraphs via `Send`, `synthesize`
  combines findings, and the streaming mapper emits only the synthesized answer.
  341 tests in `tests/agents/` + `tests/api/agent/` pass.
