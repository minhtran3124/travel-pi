---
slug: agent-task-ledger
status: proposed
owner: minh.tran
created: 2026-07-18
---

# P1 — Plan-as-state task ledger

## Design decision — the fork is resolved to Option A

**Extend `SupervisorIntent` with an ordered `plan` list (Option A), not a `write_todos`
tool (Option B).** Verified against code: the drain machinery is *already* N-capable —
`pending_flows` is a plain `list[str]` (`app/agents/state.py:64`) and `dispatch_next`
(`app/agents/nodes.py:233-268`) already pops `[0]`, keeps the rest, and fail-safes on
`booking`/unknown. Today's "one secondary intent" is just the len-1 case. So P1's only real
change is the supervisor emitting an *ordered list* instead of a single `secondary_agent`.
Option B would add a mid-turn tool-injection surface, non-deterministic state mutation, and
new streaming work for zero extra capability here — and it breaks the "LLM parses (one
structured call via `method="function_calling"`), code computes (pop/gate/cap in Python)"
pattern the codebase already commits to. Replan stays out of scope (next turn re-runs the
supervisor); no SSE change (that is P7).

## 1. Motivation

Today the supervisor queues at most ONE secondary sub-agent per turn:
`SupervisorIntent.secondary_agent` (`app/agents/supervisor.py:66-75`) becomes a
single-element `pending_flows` (`supervisor.py:287`), drained by `dispatch_next`
(`app/agents/nodes.py:233-268`) before reflection. A request like "plan my Tokyo weekend:
flights + weather + itinerary" therefore needs multiple user turns. The drain machinery is
already N-capable (see Design decision), so the single change needed is letting the supervisor
emit an *ordered plan* of follow-on sub-agents in its one structured call, so all steps run in
one turn: planner (flights) → concierge (weather) → planner (itinerary) → reflection reviews
the combined answer.

## 2. Non-goals

- **No mid-turn replan / no `write_todos` tool** (Option B rejected). The plan is fixed at
  supervisor time; re-planning is next turn's supervisor call.
- **No booking in the ledger.** Booking stays behind the HITL `plan_node` interrupt
  (`nodes.py:202-230`); the ledger type + normalization + `dispatch_next` fail-safe all
  exclude it (three layers).
- **No new "summary" sub-agent.** The example's final "summarize" is the concatenated
  sub-agent answers reviewed by reflection — not a new node.
- **No SSE / public API contract change** (that is P7). Sub-agents stream panels as today.
- **No `agent_recursion_limit` change** — the ledger cap keeps a plan inside the existing 25.

## 3. Success Criteria

- Supervisor can emit an ordered multi-step plan; `dispatch_next` runs each in order in one
  turn, then reflection, then END.
- A plan of length 0 or 1 behaves exactly like today (the 215 agent tests, incl.
  `test_multi_intent_routing.py` and `test_tier_gating.py`, stay green).
- Ledger steps are tier-gated through `AgentContext.allowed_subagents` exactly like the
  primary target; `booking` is never dispatched via the ledger.
- Ledger length is capped (`MAX_LEDGER_STEPS = 4` total sub-agent runs); a longer model-emitted
  plan is deterministically truncated in Python and a 4-step ledger completes under
  `recursion_limit=25` without `GraphRecursionError`.
- Prompt change ships as `supervisor/v7.md` + an `active.yaml` flip; no existing version file
  is edited.

## 4. Tasks

### Task 1.1 — Ordered plan in SupervisorIntent + Python normalization (wave 1)

- **Files:** apps/api/app/agents/supervisor.py, apps/api/app/agents/constants.py
- **Action:** In `constants.py` add `MAX_LEDGER_STEPS = 4` (total sub-agent runs per turn,
  including the primary target) with an inline justification: each sub-agent is an isolated
  compiled ReAct subgraph (`app/agents/subagents/_base.py`) with its own recursion budget, so
  the parent graph sees ~2 super-steps per ledger step (`dispatch_next` + the subagent node);
  4 steps stay well inside `recursion_limit=25`. In `supervisor.py`: add an optional ordered
  field `plan: list[_SecondaryTarget] | None = Field(default=None, ...)` to `SupervisorIntent`
  (reuse `_SecondaryTarget`, which already excludes `booking` at the type level) describing the
  follow-on sub-agents to run in order after `target_agent`. Keep `secondary_agent` for
  backward compat. Replace the secondary-normalization block (`supervisor.py:277-287`) with a
  deterministic builder: `raw = list(intent.plan or []) or ([secondary] if secondary else [])`;
  iterate keeping each step only if it is in `ALL_SUBAGENTS`, is not `booking`, is not already
  queued and not equal to `target` (dedupe), and passes `ctx.allowed_subagents`; stop once
  `len(pending) == MAX_LEDGER_STEPS - 1`. Assign `pending_flows = pending`. The len-1 path
  reduces to today's behavior.
- **Verify:** `../../.venv/bin/python -m pytest tests/agents/test_tier_gating.py tests/agents/test_multi_intent_routing.py tests/agents/test_supervisor.py -q`
- **Done:** New `plan` field accepted; existing tests green; single follow-on and gating
  behavior unchanged; ledger truncated to `MAX_LEDGER_STEPS`.

### Task 1.2 — Supervisor prompt v7 + active.yaml flip (wave 1)

- **Files:** apps/api/app/prompts/supervisor/v7.md, apps/api/app/prompts/active.yaml
- **Action:** Copy `supervisor/v6.md` to a new `v7.md` (never edit v6). Rewrite the "Secondary
  Intent" section into "Multi-step Plan": for a single-domain request leave `plan` null and
  route via `target_agent` only; for a request spanning several sub-agents set `target_agent`
  to the step that unblocks first and list the remaining sub-agents, in execution order, in
  `plan` (excluding the target). Restate the hard rules: `plan` never contains `booking`; no
  duplicate of `target_agent`; at most `MAX_LEDGER_STEPS-1` follow-ons (extras dropped by code).
  Add a worked example ("plan my Tokyo weekend: flights + weather + itinerary" → target=planner,
  plan=[concierge, planner]). Flip `supervisor: 6` → `supervisor: 7` in `active.yaml`.
- **Verify:** `../../.venv/bin/python -c "from app.prompts.registry import registry; assert registry.active_version('supervisor')==7; assert 'plan' in registry.get('supervisor').lower()"`
- **Done:** v7 is the active supervisor prompt and documents the ordered plan; v6 untouched.

### Task 1.3 — Refresh dispatch_next / pending_flows docs (wave 1)

- **Files:** apps/api/app/agents/nodes.py, apps/api/app/agents/state.py
- **Action:** Docs only — no behavior change. Update the `dispatch_next` docstring
  (`nodes.py:233-247`) and module header to describe draining an *ordered ledger* of sub-agent
  steps (not "at most one secondary intent"), keeping the note that the `booking`/unknown
  fail-safe stands. Update the `pending_flows` field comment (`state.py:64`) to "ordered ledger
  of follow-on sub-agents queued for this turn (P1); drained by `dispatch_next`, never contains
  booking".
- **Verify:** `ruff check app/agents/nodes.py app/agents/state.py`
- **Done:** Comments describe the ledger; lint clean; no logic touched.

### Task 2.1 — Ledger execution, gating, cap & recursion tests (wave 2)

- **Files:** apps/api/tests/agents/test_task_ledger.py
- **Action:** New test file (do not edit the passing existing files). Mirror the harness from
  `tests/agents/test_multi_intent_routing.py` (`FakeLLM(structured_responses=[...],
  responses=[...])`, `build_graph(llm=, fast_llm=, checkpointer=MemorySaver(),
  store=InMemoryStore())`). Cover: (a) a 3-step plan `SupervisorIntent(target_agent="planner",
  plan=["concierge","planner"])` runs all three sub-agents in order then reflection, with
  `pending_flows == []` at the end and message order preserved; (b) a 4-step ledger invoked with
  `{"recursion_limit": 25}` completes without `GraphRecursionError`; (c) a supervisor unit test
  (via `make_supervisor` + runtime) that a `plan` containing `booking`, a duplicate of `target`,
  and a tier-disallowed agent is filtered, and an over-long plan is truncated to
  `MAX_LEDGER_STEPS-1`; (d) a plan of length 0/1 yields identical `pending_flows` to the legacy
  `secondary_agent` path.
- **Verify:** `../../.venv/bin/python -m pytest tests/agents/test_task_ledger.py -q`
- **Done:** All ledger, gating, cap, and recursion-headroom assertions pass.

## 5. Risks

- **Recursion accounting assumption.** `MAX_LEDGER_STEPS=4` assumes sub-agent subgraphs consume
  their own recursion budget. Task 2.1(b) is the empirical guard: if a 4-step ledger throws
  `GraphRecursionError` at limit 25, lower `MAX_LEDGER_STEPS` to 3 (one constant) — do not raise
  `agent_recursion_limit`.
- **Model over-planning.** The LLM may emit long/duplicated plans; fully contained by the
  deterministic Python filter+cap in Task 1.1, reinforced by the `_SecondaryTarget` type and the
  `dispatch_next` fail-safe.
- **Prompt/graph staleness.** `active.yaml` is a pointer; the graph is baked at lifespan
  (`resolve_travel_graph`), so v7 takes effect after restart / config-generation rebuild — not
  hot-reload in a running dev server.
- **Backward compatibility.** `plan` is additive/optional; `secondary_agent` retained as the
  len-1 fallback, so directly-constructed `SupervisorIntent` objects in existing tests behave
  unchanged.

## 6. Status Log

- 2026-07-18 — Tasks 1.1, 1.2, 1.3, 2.1 implemented on `feat/agent-task-ledger`. Design fork
  resolved to Option A (extend `SupervisorIntent`). Verify: ledger suite 9 passed, full agent
  suite 224 passed (215 baseline + 9 new, no regression), ruff clean, supervisor prompt v7 active.
  Deviation (Rule 1): ordered plans are not deduplicated so a specialist may recur; legacy
  `secondary_agent` keeps its differs-from-target drop. Status → shipped-pending-review.
