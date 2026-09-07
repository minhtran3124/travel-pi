# multi-intent-single-path — Design

Status: approved at intake (option A chosen by the human, 2026-09-02). Source: deep review
2026-09-02 §3.B item 5; comparison of real use cases recorded in the intake conversation.

## Problem

Two multi-intent mechanisms coexist and only one runs:

- **Sequential ledger** (MIN-65 D4, agent-task-ledger P1, MIN-68): the supervisor writes
  `pending_flows`; `dispatch_next` drains it one specialist at a time; each follow-on sees the
  previous specialist's messages, and `superseded_message_ids` hides prior prose so it is not
  regenerated. Designed for dependent chains ("the flight picked above").
- **Parallel fan-out** (GH-117 Path A): the supervisor also writes `tasks = [target] + pending_flows`;
  `route_tasks` sends any `len(tasks) > 1` to `synthesis_worker` instances via `Send`; each worker
  gets only the last user message and its domain; `synthesize` writes one answer.

Because every non-booking turn with follow-ons has `len(tasks) > 1`, and a booking target never
has follow-ons (`supervisor.py: if target != "booking"`), the drain branch of `dispatch_next`,
`_last_subagent_answer_id`, the `superseded_message_ids` field/reducer/filter, and the mapper's
"legacy serial dispatch" token suppression are unreachable from the compiled graph. They survive
only in direct-node unit tests (`test_ledger_early_exit.py`) and in docs (`graph.py` docstring,
WORKFLOW.md §3).

Worse than dead code: the model-facing `SupervisorIntent.plan` description still says "an ORDERED
list of follow-on sub-agents to run AFTER target_agent, in execution order; a specialist MAY recur
at a later stage" — semantics the runtime cannot honor. For the flagship golden "Plan my Tokyo
weekend: find flights, check the weather, then draft an itinerary" (`plan=[concierge, planner]`)
the runtime spawns three parallel workers: the itinerary planner never sees the flights, and two
planner workers run the same query.

## Evidence that decided the fork

| Fact | Source |
| --- | --- |
| GH-117 chose parallel to fix duplicated/self-contradicting answers (REST ≠ SSE), not latency | issue #117 body |
| GH-117 knowingly bypassed `dispatch_next` for multi-intent | `specs/gh-117-agent-synthesis-send/PLAN.md:153-154` |
| Of 3 multi-intent goldens, 2 are independent slices, 1 is a dependent chain | `eval/datasets/multi_intent.json` |
| The planner alone holds `search_flights`, `search_hotels`, `search_places`, `get_weather`, `create_trip`, `add_itinerary_item`, routing — the whole dependent chain | `tools/registry.py` `TOOLS_BY_DOMAIN["planner"]` |
| Concierge-only tools are `get_local_tips`, `search_travel_knowledge`, `browse_hotels` — independent of the chosen flight | same |
| Cross-turn dependency is already served by `trip_facts` + history | `supervisor.py _normalize_slots` |

## Decision (WHAT) — option A

1. **One dispatch model: parallel, independent slices.** Delete the sequential machinery:
   `dispatch_next` (node + edges), `_last_subagent_answer_id`, `pending_flows` and
   `superseded_message_ids` (state fields, reducers, the `_base.py` visibility filter), and the
   mapper's `pending_flows` tracking / `suppress_tokens_for_current`. Sub-agent nodes edge
   directly to `reflection` (the pre-MIN-65 topology). MIN-68's clarification early-exit is kept
   by `reflection`'s existing `awaiting_user` guard.
2. **Tell the model the truth.** `SupervisorIntent.plan` becomes "additional, INDEPENDENT
   specialists whose slice does not depend on the primary's result; each runs in parallel and sees
   only this message". Remove "in execution order" and "MAY recur". `tasks` is deduplicated by
   agent (primary first, order preserved).
3. **Dependent chain → one specialist.** New supervisor prompt version (v9) adds the rule: when a
   request is a chain whose steps all live in one specialist's toolset (flights → hotel → places →
   weather → itinerary all live in planner), route to that single specialist and leave `plan` empty
   or limited to genuinely independent extras (tips/knowledge → concierge). The specialist's own
   ReAct loop is the sequential executor and sees its own tool results.
4. **Prove it.** A "plan everything" golden and a FakeLLM graph-level test that a dependent chain
   yields exactly one planner task (+ optional concierge slice), that independent slices still
   fan out and synthesize, and that a long planner loop completes within `agent_recursion_limit`.

## Non-goals

- Option B (dependency-aware serial mode), mid-turn replan, or a `write_todos` tool.
- Booking inside a plan (stays HITL-only; unchanged).
- Changing worker prompts, `synthesize`, or the SSE event contract (`reset`/`token` for
  reflection revisions stay as they are).
- Removing reflection (#112) — separate decision.

## Shape of the change (HOW)

- `app/agents/supervisor.py`: drop `pending_flows` from the Command update; build `tasks` from a
  deduplicated agent list; rewrite the `plan`/`secondary_agent` field descriptions.
- `app/prompts/supervisor/v9.md` + `active.yaml` + `CHANGELOG.md`: the "one specialist owns a
  dependent chain" routing rule with the flights→itinerary example (prompt edits need the
  version flip and a graph rebuild to take effect — `docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`).
- `app/agents/graph.py`: remove the `dispatch_next` node; `add_edge(name, "reflection")` per
  sub-agent; rewrite the module docstring topology.
- `app/agents/nodes.py`: delete `dispatch_next` and `_last_subagent_answer_id`.
- `app/agents/state.py`: delete `pending_flows`, `superseded_message_ids`, `_replace_message_ids`.
- `app/agents/subagents/_base.py`: remove the superseded filter and its docstring references.
- `app/streaming/mapper.py`: remove `pending_flows` tracking and `suppress_tokens_for_current`
  (keep the `reset` on reflection revision and the synthesis-worker prose suppression).
- `app/agents/constants.py`, `app/tools/clarification_tools.py`: comment updates only.
- Tests: retire the three direct `dispatch_next` tests; keep MIN-68 graph-level early-exit tests;
  supervisor tests read `tasks` instead of `pending_flows`; new plan-semantics + plan-everything
  tests; `test_state.py` reducer tests for the removed field go.
- Docs: WORKFLOW.md §3–4, FEATURES.md §2.1, `graph.py` docstring.

## Risks

- **Supervisor routing regression**: a new prompt version can shift routing on the routing golden
  set (baseline routing score is 0.80, memory min-58-eval-calibration). Gate with the FakeLLM
  routing tests and the multi-intent goldens; a judged eval run is advisable before merge.
- **Recursion budget**: `agent_recursion_limit = 25` per invocation; a 6–8-tool planner chain is
  12–17 steps. The plan-everything test asserts completion under the configured limit.
- **Unknown-channel crash**: the supervisor must stop emitting `pending_flows` in the same or an
  earlier wave than the state-field removal (an update key absent from the schema is an error).
- **Blast radius in tests**: seven test files mention the removed names; each is owned by a
  single task so waves stay disjoint.
