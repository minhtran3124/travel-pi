---
slug: plan-approved-reset
created: 2026-07-04
owner: Minh Tran
---

# Fix: reset plan_approved per turn (issue #63) — Intake

Lane: normal
Confidence: high
Reason: 2 flags (existing-behavior, weak-proof); logic-only reset of an internal graph-state flag — no schema, no public contract, no hard gate.
Flags: existing-behavior, weak-proof
Affects: agent HITL plan-approval state (`app/agents/nodes.py`, `app/agents/state.py`) — internal `TravelAgentState.plan_approved`, not in any API response.
Input-type: Change request (bug fix)
Route: /using-git-worktrees (branch off v3) → /subagent-driven-development
Escalate: no

## Intent

> /feature-intake for issue #63 on github

GitHub issue #63 (`bug(agent): plan_approved never reset — episodes mislabeled
outcome="approved" on later turns`):
> `plan_approved` is set `True` once when a booking plan is approved and is never reset.
> Because it lives in the LangGraph checkpointed `TravelAgentState` (per-thread), it stays
> `True` for every subsequent turn on the same conversation thread. Memory extraction reads
> it to decide episode `outcome`, so all later episodes on that thread are recorded as
> `outcome="approved"` regardless of content.
> **Suggested fix:** reset `plan_approved` to `False` at the start of each turn so the flag is
> scoped to the single turn that resumed from the approval interrupt. Add a regression test.

## Rationale

Fix at the turn-entry node `load_context_node` (`nodes.py:38`): return `plan_approved=False`.
Correctness of timing:
- `load_context` runs only on a **fresh** turn (`START → load_context`). A **resume** turn
  (`Command(resume=...)`) continues from the checkpoint at the `plan` interrupt and does NOT
  re-enter `load_context` — so the approved turn keeps `plan_approved=True` and still records
  `outcome="approved"`.
- Background memory extraction reads `plan_approved` from the **final-state snapshot** of the
  turn (`result`/sink `values`), captured before the next turn's `load_context` runs — so the
  reset never wipes the flag before extraction of the approving turn reads it.
- The next fresh turn enters `load_context`, resets to `False`; if it starts a new booking,
  `plan_node` (`nodes.py:181`) sets `True` again after `load_context`. Correct either way.

## Alternatives

- Reset in `plan_node` after consumption — rejected: extraction runs post-turn in background,
  so the flag must survive to the snapshot; resetting inside the graph turn risks clearing it
  before the background read.
- Have extraction ignore stale `plan_approved` by comparing turn identity — rejected: more
  complex, needs turn tracking the state doesn't carry.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Reset regression | `pytest tests/agents/test_hitl_plan.py -x` | 0 | 5 passed; approve→True, next turn→False |
| Contract update | `pytest tests/agents/test_state.py -x` | 0 | load_context returns `{plan_approved: False}` |
| Broad agent/mem/router | `pytest tests/agents tests/memory tests/api/agent` (`.env` aside) | 0 | 214 passed |

### Deviations

- Rule 1 — updated `test_load_context_node_no_trip_id_returns_empty` → `_resets_plan_approved`:
  load_context now returns `{plan_approved: False}` (was `{}`) by intended design.

### Rollback

- `git revert <sha>` (single-commit, reversible; flag reset is behavior-additive).
