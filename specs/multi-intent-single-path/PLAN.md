---
slug: multi-intent-single-path
status: shipped
owner: Minh Tran
created: 2026-09-02
---

# multi-intent-single-path — One dispatch model: parallel independent slices

**Base:** `main` (`54902d7`). **Branch:** `refactor/multi-intent-single-path`.
Decision (option A) and evidence in `design.md`; reuse map in `research-brief.md`.

## Global Constraints

- Waves are dependency-ordered: the supervisor must stop emitting `pending_flows` (wave 1)
  before the state field is removed (wave 2) — an update key absent from the schema errors.
- Same-wave tasks share no files. Every `Verify`/SC check is one pipe-free command under 60s
  using the env guard `env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/…`; never the
  whole suite (that runs at `finishing-a-development-branch`).
- Prompt edits go through a NEW version file + `active.yaml` flip + `CHANGELOG.md` entry; never
  edit v8 in place.
- Do not touch `synthesize`, `synthesis_worker`, the booking HITL `plan` node, or the SSE event
  schema. Stage and commit as separate commands; no Claude attribution trailers.

## 1. Motivation

See `design.md` → Problem. The runtime is parallel-only; the sequential ledger is dead code with
live tests and a model-facing description that promises what the runtime cannot do, producing a
blind itinerary worker and duplicate planners on the flagship multi-intent prompt.

## 2. Non-goals

Option B, replan, booking in a plan, worker/synthesize prompt changes, SSE contract changes,
removing reflection (#112).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | A dependent chain inside the planner toolset yields exactly one planner task (no duplicate planner workers); `plan` steps are deduplicated and never repeat the primary | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc1.db ../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py -q` | exit 0 |
| SC-2 | Independent cross-domain slices still fan out via `Send` and converge on one synthesized answer | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc2.db ../../.venv/bin/python -m pytest tests/agents/test_multi_intent_routing.py tests/agents/test_task_ledger.py -q` | exit 0 |
| SC-3 | No application Python code references the removed machinery (changelog prose documenting the removal is allowed) | `! grep -rq --include='*.py' -e pending_flows -e superseded_message_ids -e dispatch_next -e _last_subagent_answer_id apps/api/app` | exit 0 |
| SC-4 | A clarifying question still ends the turn before reflection judges it (MIN-68 preserved without `dispatch_next`) | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc4.db ../../.venv/bin/python -m pytest tests/agents/test_ledger_early_exit.py -q` | exit 0 |
| SC-5 | A multi-intent SSE turn emits one final answer: token/reset counts are unchanged after the mapper cleanup | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc5.db ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py tests/streaming -q` | exit 0 |
| SC-6 | The "plan everything" golden routes to planner (+ concierge slice) and a scripted 7-tool planner loop completes under `agent_recursion_limit` | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc6.db ../../.venv/bin/python -m pytest tests/agents/test_plan_everything.py -q` | exit 0 |

## 4. Tasks

### Task 1.1 — Supervisor semantics: truthful `plan`, dedupe, stop emitting the ledger (wave 1)

- **Files:** apps/api/app/agents/supervisor.py, apps/api/app/prompts/supervisor/v9.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/tests/agents/test_supervisor_plan_semantics.py, apps/api/tests/agents/test_task_ledger.py, apps/api/tests/agents/test_tier_gating.py, apps/api/tests/agents/test_supervisor_slots.py, apps/api/tests/agents/test_trip_facts.py
- **Action:** Rewrite the `plan` and `secondary_agent` field descriptions: additional INDEPENDENT
  specialists whose slice does not depend on the primary's result, each run in parallel on this
  message only; never the primary, never `booking`. Build `tasks` from a deduplicated agent list
  (primary first, order preserved) and drop `pending_flows` from the Command update (keep the
  state field for this wave). Add `prompts/supervisor/v9.md` = v8 + a routing rule with the
  example: a chain whose steps all live in one specialist's toolset (flights → hotel → places →
  weather → itinerary → planner) routes to that single specialist; `plan` only for genuinely
  independent extras (local tips / travel knowledge → concierge). Flip `active.yaml`, add the
  CHANGELOG entry. New `test_supervisor_plan_semantics.py` (direct supervisor calls with FakeLLM
  structured responses): `plan=[concierge, planner]` → tasks agents `[planner, concierge]`;
  `plan=[planner, planner]` → one planner task; tier gating and the booking exclusion unchanged.
  Update the listed existing tests to read `cmd.update["tasks"]` instead of `pending_flows`.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes: SupervisorIntent structured output and the prompt registry (existing). Produces: `apps/api/app/prompts/supervisor/v9.md`, `apps/api/tests/agents/test_supervisor_plan_semantics.py`, `apps/api/app/agents/supervisor.py`.
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t11.db ../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py tests/agents/test_task_ledger.py tests/agents/test_tier_gating.py tests/agents/test_supervisor_slots.py tests/agents/test_trip_facts.py tests/prompts -q`
- **Done:** supervisor never writes `pending_flows`; duplicate specialists collapse; v9 is active and registry tests pass.

### Task 2.1 — Remove the dead ledger from the graph and state (wave 2)

- **Files:** apps/api/app/agents/graph.py, apps/api/app/agents/nodes.py, apps/api/app/agents/state.py, apps/api/app/agents/subagents/_base.py, apps/api/app/agents/constants.py, apps/api/app/tools/clarification_tools.py, apps/api/tests/agents/test_ledger_early_exit.py, apps/api/tests/agents/test_multi_intent_routing.py, apps/api/tests/agents/test_state.py
- **Action:** Delete `dispatch_next` and `_last_subagent_answer_id`; remove the `dispatch_next`
  node and edge every sub-agent to `reflection` directly (`for name in SUBAGENTS:
  add_edge(name, "reflection")`); rewrite the `graph.py` module docstring to the real topology
  (supervisor → route_tasks → sub-agent | plan | Send workers → synthesize → reflection). Remove
  `pending_flows`, `superseded_message_ids` and `_replace_message_ids` from `state.py`; remove the
  visibility filter and its docstring in `_base.py`; update the `MAX_LEDGER_STEPS` comment in
  `constants.py` (it now bounds parallel workers) and the `clarification_tools.py` docstring.
  Tests: drop the three direct `dispatch_next` tests in `test_ledger_early_exit.py`, keep and if
  needed re-target its graph-level early-exit tests at `reflection`; drop `pending_flows == []`
  assertions and the module docstring in `test_multi_intent_routing.py`; drop the superseded
  reducer cases in `test_state.py`. Then re-run the tool-injection guard (`_tools_needing_trip`)
  tests to confirm the sub-agent builder is untouched.
- **Criteria:** SC-3, SC-4
- **Interfaces:** Consumes: `apps/api/app/agents/supervisor.py` (Task 1.1 — no longer emits pending_flows). Produces: `apps/api/app/agents/graph.py`, `apps/api/app/agents/state.py`, `apps/api/app/agents/nodes.py`.
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t21.db ../../.venv/bin/python -m pytest tests/agents -q`
- **Done:** the agents suite is green with no `dispatch_next` node; SC-3 grep is empty.

### Task 2.2 — Mapper cleanup: drop legacy-serial suppression (wave 2)

- **Files:** apps/api/app/streaming/mapper.py, apps/api/tests/api/agent/test_stream_events.py
- **Action:** Remove the `pending_flows` local, the `updates`-mode ledger tracking and
  `suppress_tokens_for_current`; keep the `reset` emitted when a new assistant message starts
  (reflection revision) and the synthesis-worker prose suppression. Add a multi-intent SSE test
  asserting the token/reset/subagent/done sequence for a two-slice turn (planner + concierge →
  synthesize) is: no worker prose tokens, one synthesized token stream, one `done`.
- **Criteria:** SC-5
- **Interfaces:** Consumes: the typed SSE event helpers in app/streaming/events.py (existing). Produces: `apps/api/app/streaming/mapper.py`, `apps/api/tests/api/agent/test_stream_events.py`.
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t22.db ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py tests/streaming -q`
- **Done:** SSE tests green; mapper has no reference to the ledger.

### Task 3.1 — Plan-everything golden, recursion budget, docs (wave 3)

- **Files:** apps/api/eval/datasets/multi_intent.json, apps/api/tests/agents/test_plan_everything.py, WORKFLOW.md, FEATURES.md
- **Action:** Add the golden "Plan everything for a Tokyo weekend: flights, a hotel, places to
  see, the weather, local tips and a day-by-day plan" with `expected=planner`,
  `expected_plan=['concierge']`. New graph-level FakeLLM test: supervisor returns that intent;
  the planner worker is scripted through 7 tool rounds (search_flights, search_hotels,
  search_places, get_weather, create_trip, add_itinerary_item ×2) then prose; the concierge
  worker returns tips; assert one planner task, one concierge task, a synthesized answer, and that
  the run completes with `recursion_limit=get_settings().agent_recursion_limit`. If it does not,
  STOP and report the measured step count rather than raising the limit silently. Rewrite
  WORKFLOW.md §3 topology and the dispatch/ledger paragraphs and FEATURES.md §2.1 to the single
  parallel model.
- **Criteria:** SC-6
- **Interfaces:** Consumes: `apps/api/app/agents/graph.py` (Task 2.1) and `apps/api/app/agents/supervisor.py` (Task 1.1). Produces: `apps/api/tests/agents/test_plan_everything.py`, `apps/api/eval/datasets/multi_intent.json`.
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/t31.db ../../.venv/bin/python -m pytest tests/agents/test_plan_everything.py -q`
- **Done:** golden present; plan-everything test green under the configured limit; docs match the graph.

## 5. Risks

- Routing shift from prompt v9 on the routing golden set; mitigated by the FakeLLM routing tests in
  wave 1 and a judged eval run recommended before merge (baseline routing 0.80).
- Recursion budget for a long planner loop; measured by Task 3.1, with an explicit STOP instead of a
  silent limit bump.
- Seven test files mention the removed names; each is owned by one task so waves stay disjoint.
- `remove-functionality` judgment gate: the removed paths are unreachable in the compiled graph
  (design.md → Problem); no user-visible behavior is lost.

## 6. Status Log

- 2026-09-02 — intake complete (feature-intake); fork resolved by the human (option A); plan proposed, not yet executed.

- 2026-09-02 — task 1.1 complete; commit 09d2fc5 (wave 1). 93 tests pass; supervisor v9 active; supervisor stops writing pending_flows and dedupes tasks. Review (mi-rev-1): SPEC+QUALITY PASS, no Critical/Important. Deviation (Rule 2): test_multi_intent_routing.py 3 lines changed to out.get("pending_flows",[]) to survive the wave-1 supervisor change (a wave-2 file; folded forward). Minors deferred: v9 example lists weather under planner though WEATHER_TOOLS is shared with concierge (rule 3 is multi-domain-only; the "weather in Bali → concierge" golden in wave 3 guards it); dispatch_next docstring still describes pending_flows as live (removed in wave 2).

- 2026-09-02 — tasks 2.1, 2.2 complete; commit d3df354 (wave 2). Combined re-verify 432 passed (agents + agent API + streaming); SC-3 satisfied (no app .py references; only CHANGELOG prose documents the removal, so SC-3 was scoped to --include=*.py). Review (mi-rev-2): SPEC+QUALITY PASS, no Critical/Important; removal clean, no broken path (graph edges sub-agents→reflection, booking HITL + synthesize intact, REVISE re-entry works, MIN-68 via reflection awaiting_user guard). Deviations (Rule 3): deleted two tests exercising the removed machinery. Minors deferred: the relocated "booking never a parallel task" guard has no direct assertion (type+code both forbid it); a multi-intent worker that asks for clarification has its question folded into synthesize rather than surfaced verbatim (ends cleanly, design nuance).

- 2026-09-02 — task 3.1 complete (commit cdb6d6a); SHIPPED. Final chain: correctness-review SHIP (434 passed; graph integrity, dedupe, MIN-68, SSE single answer, recursion budget all confirmed — each sub-agent subgraph gets a fresh budget so parent superstep ~6-8), intent-review PASS (all five option-A deliverables land, no drift/excess). verify_summary --check: SC-1..SC-6 all re-run green. Receipt at .review-receipt.json. Follow-ups (SUMMARY Not-auto-verified): a real-LLM judged eval of routing (v9) and of a real "plan everything" turn.
