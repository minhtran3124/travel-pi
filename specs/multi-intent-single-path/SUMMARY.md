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

_(pending — written at implementation)_

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

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| <unit> | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/x.db ../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py -q` | — | not yet run | SC-1 |

### Not auto-verified

- Real-LLM quality of a "plan everything" turn (does the model actually complete flights →
  hotel → places → weather → itinerary in one planner loop?) — reached traceability only via a
  FakeLLM-scripted golden and the recursion-budget check; a judged eval run is the truth-tier
  check and needs a provider key (see `apps/api/eval/`).

### Rollback

- `git revert <sha>` per commit. The removed machinery is dead in the compiled graph, so reverting
  restores no user-visible behavior; the supervisor prompt flip is reverted by pointing
  `prompts/active.yaml` back at v8.

### Harness-Delta

- none yet
