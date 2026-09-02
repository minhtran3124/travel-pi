# multi-intent-single-path — Summary

Lane: high-risk
Confidence: high
Reason: judgment hard gate `remove-functionality` fires (deleting the sequential task-ledger path — dead in the compiled graph but present, with tests asserting it) plus flags existing-behavior, multi-domain (agent graph/state/supervisor/prompt/streaming mapper/tests/docs) and weak-proof (must prove independent fan-out is unchanged and the dependent flagship prompt improves). Direction was a real design fork (A vs B) and was resolved by the human at intake, so confidence is high.
Flags: existing behavior, multi-domain, weak proof, model-facing contract (`SupervisorIntent.plan` description)
Affects: apps/api/app/agents/{graph,nodes,state,supervisor}.py, agents/subagents/_base.py, streaming/mapper.py, prompts/supervisor (new version + active.yaml), tests/agents/*, WORKFLOW.md
Input-type: change request
Route: high-risk — design.md → research-brief.md → PLAN.md (this dir) → using-git-worktrees → subagent-driven-development
Escalate: no (fork resolved at intake: option A)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> check for "Hai cơ chế multi-intent chồng nhau, một cái không còn reachable", create design +
> spec with /feature-intake
>
> (deep review 2026-09-02 §3.B item 5) Hai cơ chế multi-intent chồng nhau, một cái không còn
> reachable. Supervisor phát ra cả `pending_flows` (ledger tuần tự, MIN-65/68) lẫn `tasks`
> (GH-117). Vì `tasks = [target] + pending_flows` và `route_tasks` đẩy mọi `len(tasks)>1` sang
> Send song song, nhánh `dispatch_next` drain + `superseded_message_ids` không bao giờ chạy trong
> graph compile, nhưng vẫn maintain/test. WORKFLOW.md + docstring graph.py mô tả topology cũ.
>
> (human, on the comparison) "So sanh use case song song và tuần tự trong thực te voi project
> nay" → after the comparison: "Chọn A" — one path: parallel-independent; delete the dead
> sequential ledger; fix the `plan` description so the model plans INDEPENDENT slices; dedupe
> recurring specialists; and route a dependent chain that lives inside one specialist's toolset
> to that single specialist (the planner's own ReAct loop is the sequential executor).

## What changed

Collapsed the two overlapping multi-intent mechanisms into one across three waves:

- **Wave 1 (supervisor):** stops writing the dead `pending_flows` channel; builds `tasks` from a
  deduplicated agent list (primary first, recurring specialists collapsed); rewrites the
  model-facing `SupervisorIntent.plan`/`secondary_agent` descriptions to "independent parallel
  slices, never the primary, never booking"; ships supervisor prompt v9 with the rule that a
  dependent chain living inside one specialist's toolset routes to that single specialist.
- **Wave 2 (removal):** deletes `dispatch_next`, `_last_subagent_answer_id`, the `pending_flows`
  and `superseded_message_ids` state fields + reducer, the sub-agent visibility filter, and the
  mapper's legacy-serial suppression. Every sub-agent edges straight to reflection; MIN-68
  clarification early-exit is preserved by reflection's `awaiting_user` guard.
- **Wave 3 (proof + docs):** a "plan everything" golden and a graph-level test proving a
  seven-tool planner chain plus a concierge slice completes in a measured 22 super-steps under
  the configured `agent_recursion_limit` of 25; WORKFLOW.md and FEATURES.md rewritten to the
  single parallel model.

### Rationale

GH-117 replaced the sequential ledger with parallel `Send` fan-out to fix issue #117 (each queued
specialist regenerated the whole answer → duplicated, self-contradicting REST replies). It bypassed
`dispatch_next` for every multi-intent turn but left the drain, `superseded_message_ids` and the
mapper's legacy-serial suppression in place as unreachable code, and left the model-facing `plan`
description promising ordered, dependent, recurring execution the runtime no longer performs — so
the flagship "plan my weekend: flights, weather, then itinerary" prompt spawns a blind itinerary
worker plus a duplicate planner. Option A makes the shipped model the only model, tells the model
the truth about it, and serves the one dependent golden through the planner's own ReAct loop,
which already holds every tool that chain needs.

### Alternatives considered

- B) Two real modes (dependency signal on the intent; dependent chains routed serially through
  `dispatch_next`, independent slices in parallel) — rejected by the human: re-inherits the
  regenerate-whole-answer defect that produced #117 unless specialists are also changed to
  contribute slices, i.e. a new feature, not a cleanup; the golden set shows no cross-domain
  dependent chain that one specialist cannot own.
- C) Docs-only — rejected: leaves dead code, tests asserting fiction, a lying schema description
  and duplicate workers.

### Deviations

- Rule 2 (wave 1): `test_multi_intent_routing.py` (a wave-2 file) got a 3-line `out.get("pending_flows", [])`
  fix so the suite survived the supervisor change; superseded by wave 2's edits to the same file.
- Rule 3 (wave 2): deleted two tests that directly exercised the removed machinery
  (`test_pending_flows_field_in_state_schema`, `test_dispatch_next_refuses_illegal_queued_flow`);
  the booking-never-a-follow-on invariant they guarded is now enforced upstream by both the
  `_SecondaryTarget` type and the supervisor code.
- Rule 1 (wave 3): the plan-everything test uses a per-specialist scripted model instead of one
  shared FakeLLM, because the two parallel workers run on concurrent threads and interleave a
  shared response cursor — a real property of the parallel model, not a test artifact.
- Controller: SC-3's grep was scoped to `--include='*.py'` after review — the unscoped grep matched
  the CHANGELOG/FEATURES prose that documents the removal by name, which is desirable, not a
  violation.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Dedupe + route-to-one | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc1.db ../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py -q` | 0 | plan excludes primary; no duplicate specialists | SC-1 |
| Independent fan-out | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc2.db ../../.venv/bin/python -m pytest tests/agents/test_multi_intent_routing.py tests/agents/test_task_ledger.py -q` | 0 | slices still Send-fan-out + synthesize | SC-2 |
| No dead-code refs | `! grep -rq --include='*.py' -e pending_flows -e superseded_message_ids -e dispatch_next -e _last_subagent_answer_id apps/api/app` | 0 | app Python only; CHANGELOG prose allowed | SC-3 |
| MIN-68 preserved | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc4.db ../../.venv/bin/python -m pytest tests/agents/test_ledger_early_exit.py -q` | 0 | clarify ends turn via reflection guard | SC-4 |
| SSE single answer | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc5.db ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py tests/streaming -q` | 0 | multi-intent streams one synthesized answer | SC-5 |
| Plan-everything in budget | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc6.db ../../.venv/bin/python -m pytest tests/agents/test_plan_everything.py -q` | 0 | 22 super-steps < 25 limit | SC-6 |

### Not auto-verified

- Real-LLM quality of a "plan everything" turn (does the model actually complete flights →
  hotel → places → weather → itinerary in one planner loop?) — reached traceability only via a
  FakeLLM-scripted golden and the recursion-budget check; a judged eval run is the truth-tier
  check and needs a provider key (see `apps/api/eval/`).
- Recursion headroom is thin: the scripted 7-tool chain measured 22 of 25 super-steps. A real
  planner that takes more tool rounds (retries, an 8th step) could approach the limit; a
  follow-up should either cap planner tool rounds or raise `agent_recursion_limit` if judged
  runs show real "plan everything" turns nearing 25.
- Supervisor routing on the full routing golden set under a real judge (prompt v9 could shift
  routing; baseline ~0.80) — provider-key eval, not run here. The FakeLLM suites and the
  "weather in Bali → concierge" golden guard the obvious regressions.

### Rollback

- `git revert <sha>` per commit. The removed machinery is dead in the compiled graph, so reverting
  restores no user-visible behavior; the supervisor prompt flip is reverted by pointing
  `prompts/active.yaml` back at v8.

### Harness-Delta

- backlog: SC-style dead-code grep checks should default to `--include='*.py'` — an unscoped
  grep matches changelog/feature-doc prose that legitimately names the removed symbol.
- backlog: `hooks/lib/lane.sh` single-active-plan assumption still mis-aims the blast-radius hook
  at a stale `conversation-persistence` plan on every edit this session (also seen in the prior spec).
