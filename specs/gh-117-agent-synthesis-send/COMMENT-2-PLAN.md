---
slug: gh-117-agent-synthesis-send
status: shipped
owner: minh.tran
created: 2026-08-14
---

# GH-117 Path A follow-up — Preserve worker state mutations (Codex Comment 2)

## 1. Problem

PR #122 review comment #2:

> For multi-intent turns, the inner specialist may update graph state through
> tools — for example, `create_trip` sets the new `trip_id`, and
> `needs_clarification` sets `awaiting_user` — but this return path propagates
> only `task_results`. The database side effect can therefore succeed while the
> parent checkpoint and API response retain no active trip, and clarification
> signals never reach reflection.

Currently `synthesis_worker` runs the inner specialist, extracts the final
assistant prose as `findings`, and returns **only** `task_results`. Any state
mutation performed by tools inside the worker is discarded.

## 2. Research findings

### 2.1 Tools that mutate graph state

A full audit of `app/tools/*.py` found only two state-mutating code paths:

| Tool | State field changed | Trigger |
|------|---------------------|---------|
| `needs_clarification` | `awaiting_user = True` | Any sub-agent decides it is blocked on the traveller (MIN-68). |
| `create_trip` (anonymous caller) | `awaiting_user = True` | Anonymous user tries to create a trip (#118). |
| `create_trip` (success) | `trip_id = <new_trip_id>` | Planner creates a new trip. |

All other tools either:
- Read from `InjectedState` (`trip_id`, `user_id`, `preferences`) and return
  plain data, or
- Write to external stores (DB, `BaseStore` for memory) and return plain data.

They do **not** return `Command(update=...)` that touches `TravelAgentState`.

### 2.2 Why this matters for multi-intent

Example turn: *"Plan a 3-day Da Nang trip and check the weather there"*

- Supervisor emits tasks: `[planner, concierge]`.
- The planner worker calls `create_trip` and sets `trip_id` in its inner state.
- The concierge worker uses `get_weather` and returns prose.
- Synthesis combines both findings.

Without propagation, the checkpoint after the turn still has `trip_id = None`.
The client receives `trip_id: null` even though a real trip row exists in the DB.
On the next turn the agent has no active trip context.

Example turn: *"Find flights to Tokyo and things to do there"* where the planner
is missing a departure city.

- Planner worker calls `needs_clarification` → inner `awaiting_user = True`.
- Without propagation, parent `awaiting_user` stays `False`.
- Reflection does not short-circuit; it judges the incomplete answer and may
  REVISE instead of ending with a clarifying question.

### 2.3 What must NOT propagate

The worker must remain a **closed box** for most inner state:

- `messages` — inner tool calls, tool results, and assistant prose must not leak
  into the parent transcript; only the synthesized answer becomes a parent
  message.
- `current_flow` — the worker already overrides this locally; parent
  `current_flow` is managed by the supervisor/static path.
- `tasks`, `pending_flows`, `superseded_message_ids` — scheduling state owned by
  the supervisor and `dispatch_next`.
- `revisions` — reflection counter.

## 3. Proposed fix

### 3.1 Merge a small whitelist of mutated fields

In `app/agents/subagents/synthesis_worker.py`, after `subagent.invoke(...)`:

1. Capture the input state snapshot (`inner_state`) before the sub-agent runs.
2. Compare the inner result against that snapshot for the whitelisted fields:
   - `trip_id`
   - `awaiting_user`
3. Include only the fields that actually changed in the worker's
   `Command(update=...)`.

Why compare instead of blindly copying:
- Avoids overwriting a `trip_id` created by a parallel worker with `None` from a
  worker that did not create a trip.
- Avoids resetting `awaiting_user = True` from one worker with `False` from
  another (the `last_write_wins` reducer would still mishandle parallel writes
  if every worker emits a value).

### 3.2 Whitelist rationale

Only `trip_id` and `awaiting_user` are emitted by tools today. Keeping the list
explicit prevents accidental leakage of inner subgraph state and makes future
audits easy. If a new tool later mutates another state field, the whitelist
forces a conscious decision about whether that mutation is safe to propagate
from a parallel worker.

### 3.3 Edge cases

- **Parallel `trip_id` conflicts:** if two workers both create trips, both will
  emit different `trip_id` values. `trip_id` has no reducer, so LangGraph will
  raise `InvalidUpdateError`. This is correct behavior — a single turn should
  not create two active trips.
- **One worker clarifies, another succeeds:** `awaiting_user` has a
  `last_write_wins` reducer. Only the worker that called `needs_clarification`
  emits `True`; others emit nothing. The final value will be `True`, reflection
  will short-circuit, and the clarifying finding will be synthesized into the
  final question.
- **Anonymous `create_trip`:** the tool itself sets `awaiting_user = True`
  instead of `trip_id`; the same propagation logic handles it.

## 4. Implementation

### 4.1 Files touched

- `apps/api/app/agents/subagents/synthesis_worker.py`
- `apps/api/tests/agents/test_multi_intent_routing.py` (new regression tests)
- Optional cleanup: remove the dead `synthesis_worker` stub in
  `apps/api/app/agents/nodes.py`.

### 4.2 Code change sketch

```python
def build_synthesis_worker(resolve_model):
    def worker(state, runtime):
        task = state.get("task") or {}
        agent_name = task.get("agent", "unknown")
        index = task.get("index", 0)

        builder = _AGENT_BUILDERS.get(agent_name)
        if builder is None:
            ...

        inner_state = dict(state)
        inner_state["task"] = task
        inner_state["current_flow"] = agent_name
        result = subagent.invoke(inner_state, config=getattr(runtime, "config", None))
        findings = _last_assistant_content(result.get("messages", []))

        # Propagate state mutations produced by tools inside the worker.
        state_updates = {}
        for key in ("trip_id", "awaiting_user"):
            new_val = result.get(key)
            if new_val != inner_state.get(key):
                state_updates[key] = new_val

        return Command(
            update={
                "task_results": [
                    {"agent": agent_name, "index": index, "findings": findings}
                ],
                **state_updates,
            },
            goto="synthesize",
        )
    return worker
```

### 4.3 Tests

Add two integration tests to `tests/agents/test_multi_intent_routing.py`:

1. **`test_worker_propagates_created_trip_id_to_parent`**
   - Supervisor emits `[planner, concierge]`.
   - FakeLLM drives the planner worker to call `create_trip`.
   - Assert the final parent state has a non-null `trip_id` and the synthesized
     answer references the trip.

2. **`test_worker_propagates_awaiting_user_to_parent`**
   - Supervisor emits `[planner, concierge]`.
   - FakeLLM drives the planner worker to call `needs_clarification`.
   - Assert parent `awaiting_user` is `True` and reflection ends immediately
     (no revision).

For `create_trip`, the test must point `DATABASE_URL` at the same temp SQLite
file used by the graph so the tool writes are visible, mirroring
`test_trip_id_persists_across_turns_after_create_trip`.

## 5. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Accidentally leak inner `messages` to parent | Whitelist only `trip_id` and `awaiting_user`; never copy `messages`. |
| Parallel workers overwrite each other's `trip_id` | Compare values and emit only when changed; LangGraph raises on true conflict. |
| Future tool adds a new state mutation | Whitelist forces an explicit decision; add a code comment pointing to this plan. |
| Tests become flaky due to parallel worker ordering | FakeLLM responses are consumed in deterministic LangGraph order observed in existing tests; if ordering changes, pin it with targeted logging or explicit task/agent checks. |

## 6. Verification

- `DATABASE_URL=sqlite:///:memory: python -m pytest tests/agents/ tests/api/agent/ tests/eval tests/streaming -q` → 424+ passed.
- Real eval with `gpt-4o-mini`: routing/plan/task accuracy ≥ thresholds.
- New regression tests for `trip_id` and `awaiting_user` propagation pass.
