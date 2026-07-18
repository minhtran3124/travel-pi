# agent-task-ledger — Summary

Lane: normal
Confidence: medium
Reason: Rewrites shipped, test-covered dispatch behavior (#8) and touches the tier-gating enforcement path (#2) while preserving its semantics — 2 flags, no hard gate; design choices within the plan have reasonable defaults.
Flags: authorization (enforcement path preserved, not changed), existing behavior
Affects: apps/api/app/agents/ (state.py, nodes.py dispatch_next, supervisor structured output + prompt) — internal graph behavior; no public API/SSE contract change
Input-type: spec slice

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> /feature-intake for P1 from doc research specs/agentic-chatbot/research-brief.md

P1 as defined in `specs/agentic-chatbot/research-brief.md` §3:

> **P1 — Plan-as-state task ledger (the core "more agentic" unlock)**
> Generalize `dispatch_next` from "one queued secondary intent" to a real task queue.
> `state.py:64` already types `pending_flows`; add a `todos` state key + a supervisor-writable
> plan (`write_todos`-style tool or structured output extension of `SupervisorIntent`).
> Sub-agents execute items; `dispatch_next` pops until done or budget hit. Enables
> "plan my Tokyo weekend" → search flights → check weather → build itinerary → summarize,
> in one turn. *Seam:* `agents/nodes.py:233`, `agents/state.py`, supervisor prompt v7.

Scope boundaries from the same brief: P2 (tiered HITL), P7 (SSE `plan` event) are separate
paths — P1 stays internal to the graph. Constraints (§5): ledger on the fast model, cap ledger
length, respect `agent_recursion_limit=25`, respect tier gating (`AgentContext.allowed_subagents`),
booking never auto-dispatched.

## What changed

The supervisor can now emit an ordered `plan` of follow-on sub-agents (new optional field on
`SupervisorIntent`), and the existing `dispatch_next` node drains it in one turn. A request
spanning several specialists (e.g. "plan my Tokyo weekend: flights + weather + itinerary") now
runs planner → concierge → planner in a single turn instead of forcing multiple user turns.
Added `MAX_LEDGER_STEPS = 4` (cap), supervisor prompt `v7` (documents the ordered plan), and a
new `test_task_ledger.py` suite. Legacy `secondary_agent` retained as the len-1 fallback.

### Rationale

Option A (extend `SupervisorIntent`) over Option B (`write_todos` tool): the drain machinery is
already N-capable — `pending_flows` is a plain `list[str]` and `dispatch_next` already pops `[0]`,
keeps the rest, and fail-safes on `booking`/unknown. So the only real change is the supervisor
emitting an ordered list, preserving the "LLM parses (one structured call), code computes
(pop/gate/cap in Python)" pattern. Booking exclusion is three-layered (type `_SecondaryTarget` +
`target == "booking"` empties the ledger + `dispatch_next` fail-safe).

### Alternatives considered

- **Option B — a `write_todos` tool** the supervisor calls mid-turn: rejected. Adds a
  tool-injection surface, non-deterministic state mutation, and streaming work for zero extra
  capability, and breaks the deterministic one-structured-call pattern.

### Deviations

- Rule 1 — Ordered plans are **not** deduplicated (a specialist may legitimately recur, e.g.
  planner for flight-search then itinerary). The initial filter dropped `step == target` /
  prior duplicates, which broke the motivating example; corrected so only the *legacy*
  `secondary_agent` path keeps the old "differs from target" no-op drop. `supervisor.py`.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| New ledger suite | `DATABASE_URL=sqlite:///:memory: python -m pytest tests/agents/test_task_ledger.py -q` | 0 | 9 passed (order, recursion headroom, tier-gate, cap, type-level booking block, legacy compat) |
| Full agent regression | `DATABASE_URL=sqlite:///:memory: python -m pytest tests/agents/ -q` | 0 | 224 passed (215 baseline + 9 new; no regression) |
| Prompt registry | `python -c "from app.prompts.registry import registry; assert registry.active_version('supervisor')==7"` | 0 | v7 active, `plan` documented |
| Lint | `ruff check app/agents/{supervisor,constants,nodes,state}.py tests/agents/test_task_ledger.py` | 0 | clean |

### Rollback

- `git revert <sha>` (additive optional field + dispatcher docs + new prompt version; no
  migration, no schema change). To revert the prompt only: flip `active.yaml` `supervisor: 7` → `6`.

### Harness-Delta

- none
