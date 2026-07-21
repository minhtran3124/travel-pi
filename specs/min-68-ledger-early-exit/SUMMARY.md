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

A sub-agent blocked on the traveller can now short-circuit the task ledger. New Command-returning `needs_clarification` tool (unregistered — off MCP//agent/manifest) sets a single-turn `awaiting_user` flag (last-write-wins reducer; reset by `load_context` each turn); `dispatch_next` then abandons the remaining `pending_flows` and routes straight to reflection instead of draining queued sub-agents whose output the traveller never sees. The tool is appended to every specialist in `build_subagent`, and `communication_style` v7 teaches when to call it (once, only when traveller-blocked; never for tool failures). Commits: `1460c26` (wave 1), `b8336d1` (wave 2), `6f13aaf` (correctness fix). Review chain: per-task spec + quality ✅, adversarial correctness (6 angles → 1 confirmed fix + 5 advisories), intent review ✅.

### Rationale

Abandon-not-park chosen by the user at intake: the clarifying answer often invalidates the parked steps anyway, and re-planning costs one supervisor round-trip vs staleness/invalidation complexity in state. Signal mechanism intentionally left to PLAN.md so it can be weighed against existing sub-agent/tool patterns.

### Alternatives considered

- Park-and-resume the remaining ledger steps across turns — rejected at intake (staleness/invalidation complexity outweighs the saved planning round-trip).

### Deviations

- Rule 1 — Pre-existing exact-shape assert `load_context_node(...) == {"plan_approved": False}` broke on the additive `awaiting_user` key; extended to include `"awaiting_user": False` (+1 docstring line). `apps/api/tests/agents/test_state.py`. Commit `1460c26`. Plan gap: file was missing from Task 1.1's Files set (same class as docs/solutions/harness/sse-additive-field-breaks-cross-dir-shape-test.md).
- Rule 1 — Correctness-review finding (empirically reproduced): duplicate parallel `needs_clarification` calls crashed the turn with `InvalidUpdateError` (plain LastValue channel, two Command writes in one superstep). Fixed with a `last_write_wins` reducer on `awaiting_user` + graph-level regression test. `apps/api/app/agents/state.py`, `apps/api/tests/agents/test_ledger_early_exit.py`. Commit `6f13aaf`.

### Advisory Findings

Correctness-review findings scoring below the fix-loop threshold (80) — recorded, not auto-fixed:

- (50, **RESOLVED** in `fc9e213`) **Reflection may REVISE a clarifying question** — the early exit routes to `reflection`, whose prompt says REVISE on "incomplete" answers; a clarifying question is by construction incomplete. A REVISE would pressure the blocked sub-agent to answer without the missing detail (fabrication risk MIN-67 class) and, on SSE, replace the streamed question. Scored 50 here (trigger depends on the judge LLM's verdict), but the PR #105 external review (Codex) escalated it to P1, so it was fixed: `reflection()` now returns `Command(goto=END)` when `awaiting_user` is set, before the judge call. Covered by `test_reflection_skips_when_awaiting_user` + graph-level `test_blocked_turn_survives_revise_prone_reflection`. `apps/api/app/agents/nodes.py`.
- (50) **False-positive latch** — nothing in code un-sets `awaiting_user` within a turn: if the model calls the tool but then self-recovers and answers fully without asking, the queued follow-ons are still abandoned. Guard is prompt-only ("call ONCE… then ask"). Possible hardening: corroborate the latch against the final AIMessage in `dispatch_next`. `apps/api/app/tools/clarification_tools.py` + `apps/api/app/agents/nodes.py:260-266`.
- (50) **`graceful_fallback` may discard the tool's Command** — in TOOL_FAULT sub-agents, a sibling I/O tool exhausting retries with a non-ToolException fails the whole tools node; the fallback emits GRACEFUL_MSG for every call id incl. `needs_clarification`, and the flag write may be lost (LangGraph merge behavior under error_handler unconfirmed; same latent shape pre-exists with `create_trip`). `apps/api/app/agents/retry.py:75-98` (unmodified-line interaction).
- (0, pre-existing) **`revisions` never resets per turn** — the reflection counter persists in the checkpoint; after one REVISE anywhere in a thread, reflection is silently disabled for that conversation's lifetime (`revisions >= max_revisions` forever). Reported by 3 independent angles. Fix would be `"revisions": 0` in `load_context_node`'s reset dict — out of this branch's scope (unmodified lines). `apps/api/app/agents/nodes.py:73,175-193`.
- (0, no wrong outcome) **SSE emits `needs_clarification` tool_call events** — mapper emits them like any tool, but the FE explicitly ignores `tool_call`/`tool_result` events (`apps/web/src/components/chat/useAgentStream.ts` — "not surfaced"), and mapper lines are unmodified. Cosmetic at most.

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

- `git revert 6f13aaf b8336d1 1460c26` (code commits, newest first; prompt rollback alternative: set `communication_style: 6` in `app/prompts/active.yaml`)

### Harness-Delta

- none
