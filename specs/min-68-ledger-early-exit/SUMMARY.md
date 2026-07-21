# min-68-ledger-early-exit — Summary

Lane: normal
Confidence: medium
Reason: Flags 8 (test-covered ledger-drain behavior changes) and 9 (no proof exists yet around a "blocked" path) fired; no hard gates — traveller-visible reply is unchanged, no auth/migration/API-envelope change.
Flags: existing behavior, weak proof
Affects: agent graph — apps/api/app/agents/nodes.py (dispatch_next), state.py (TravelAgentState), supervisor.py (pending_flows writer)
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

From GitHub issue #99 (minhtran3124/travel-pi, "Task ledger has no early exit: queued steps drain even when the agent is blocked on the traveller", Linear MIN-68), verbatim:

> Once the supervisor emits a multi-step `plan`, every queued step drains unconditionally. If the first specialist concludes it is **blocked** and needs to ask the traveller a clarifying question, the remaining follow-ons still run, spend LLM and tool calls, and produce nothing the traveller ever sees.

> `dispatch_next` (`apps/api/app/agents/nodes.py`) drains `pending_flows` purely on queue emptiness. There is no signal a sub-agent can raise to say "I am blocked on the traveller; abandon the rest of the plan". The ledger is fire-and-forget once the supervisor writes it.

> Give a sub-agent a way to short-circuit the ledger — e.g. a state flag (`awaiting_user` / `blocked`) that `dispatch_next` checks before popping the next step, clearing `pending_flows` and routing straight to reflection/END.

> Worth deciding explicitly: should a clarification abandon the plan entirely, or park it so the next turn resumes the remaining steps instead of re-planning from scratch?

Intake decisions (user, 2026-07-20): (1) exit policy — **abandon the plan** (clear `pending_flows`, route to reflection/END; next turn re-plans with the clarified info); (2) signal mechanism (dedicated tool vs prompt + state flag) — **deferred to the planning phase**.

## What changed

<pending — filled at completion>

### Rationale

Abandon-not-park chosen by the user at intake: the clarifying answer often invalidates the parked steps anyway, and re-planning costs one supervisor round-trip vs staleness/invalidation complexity in state. Signal mechanism intentionally left to PLAN.md so it can be weighed against existing sub-agent/tool patterns.

### Alternatives considered

- Park-and-resume the remaining ledger steps across turns — rejected at intake (staleness/invalidation complexity outweighs the saved planning round-trip).

### Deviations

- Rule 1 — Pre-existing exact-shape assert `load_context_node(...) == {"plan_approved": False}` broke on the additive `awaiting_user` key; extended to include `"awaiting_user": False` (+1 docstring line). `apps/api/tests/agents/test_state.py`. Commit `1460c26`. Plan gap: file was missing from Task 1.1's Files set (same class as docs/solutions/harness/sse-additive-field-breaks-cross-dir-shape-test.md).

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Baseline before branch work | `cd apps/api && ../../.venv/bin/python -m pytest tests/ -q` (.env moved aside) | 0 | 1743 passed, 63s |
| Task 1.1 unit tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_ledger_early_exit.py -x -q` | 0 | 4 passed |
| Task 1.2 tool tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_clarification_tools.py -x -q` | 0 | 2 passed |
| Wave-1 regression (agents) | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/ -q` | 0 | 232 passed after test_state.py exact-shape fix |
| Task 2.1 verify (ledger + registry) | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_ledger_early_exit.py tests/agents/test_task_ledger.py tests/tools/test_tool_registry.py -q` | 0 | 64 passed; re-run by controller and both reviewers |
| Wave-2 regression (agents + prompts) | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/ tests/prompts/ -q` | 0 | 249 passed (quality reviewer re-run); 2 pre-existing failures in tests/tools/test_routing_tools.py are env-dependent (live ORS key), present on the unmodified tree |

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
