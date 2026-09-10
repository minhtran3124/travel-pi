# specialist-task-description — Summary

Lane: normal
Confidence: medium
Reason: No manifest hard gate fires (no auth, migration, route, provider or high-blast file); two flags fire — existing-behavior (every specialist turn's model input changes and SupervisorIntent's structured output grows a per-task query) and weak-proof (the behaviour is prompt-driven; offline tests can pin the plumbing but the value claim needs a judged eval golden), and the diff spans >2 files — so normal, not tiny.
Flags: existing-behavior, weak-proof
Affects: agent supervisor structured output (`SupervisorIntent`/`AgentTask.query`), specialist input assembly (`subagents/_base.py`), fan-out worker (`synthesis_worker.py`), supervisor prompt (new `supervisor/v13.md` + `active.yaml`), eval goldens (`eval/datasets/routing.json`)
Input-type: change request
Route: using-git-worktrees → xia2 (Standard) → writing-plans → subagent-driven-development
Escalate: no (notify-and-proceed; the two open forks below have documented defaults and are decided in PLAN.md, not by a human)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

User message (2026-09-10):

> following artifact
> /feature-intake for "Fork kèm task description cho specialist"

The "following artifact" is step 2 of the architecture review *Fork hay Isolated*
(https://claude.ai/code/artifact/13ac09dc-4c58-4c32-8ba9-e0ef664d1cee, 2026-09-10), quoted verbatim as the scope-deciding text:

> **Fork kèm task description cho specialist**
> Supervisor sinh `query` riêng cho từng task thay vì copy nguyên câu user. Trong `_base.py`, nối task text vào cuối input của specialist với preamble cố định, đúng cách blog mô tả. Đặc biệt có lợi cho fan-out song song, nơi 3 worker hiện phải tự đoán phần việc.
>
> Gotcha đã ghi nhận: chèn `HumanMessage` tổng hợp từng làm flip ngôn ngữ và kích hoạt rule "traveller's latest message" trong prompt. Đưa task qua `SystemMessage` cuối hoặc ghép vào system prompt, không dùng user message. Cần thêm golden multi-intent để đo.
>
> giá trị cao · 2 file

## What changed

Each specialist now receives the supervisor's task for its own slice of the message. The supervisor emits `task_queries` (supervisor prompt v13), and each `AgentTask.query` carries that specialist's part instead of the whole user sentence. A malformed or misaligned list falls back to the user message. `_base.py` appends the query to the specialist's model input as a trailing `SystemMessage` behind `TASK_NOTE_PREAMBLE`. The note is built per call and never stored. On the fan-out path `synthesis_worker` hands the task over through the declared `tasks` key. Two fan-out goldens and a judged `ask_coverage` rubric measure the effect.

### Rationale

Intake facts that fix the lane (all read from the tree at 34f9920):

- `app/agents/supervisor.py:368-378` builds every `AgentTask` with `query=last_user_message` — the same full user sentence for all N tasks. `AgentTask.query` (`app/agents/schemas.py:21`) already exists and is documented as "the user-facing request specific to this specialist", but no consumer reads it: grep `\.get("query")|\["query"\]|task\.query` over `app/agents` → 0 hits outside the constructor.
- `app/agents/subagents/_base.py` `assistant()` invokes `[system_msg, *state["messages"]]` — the full-history fork the blog describes, with no task text. `synthesis_worker.py` deep-copies the same history into each parallel worker and sets `inner_state["task"]`, which the inner subgraph likewise never reads.
- The delivery channel is already decided by a recorded failure: `docs/solutions/agent/reflection-humanmessage-language-flip.md` (critical) — internal steering text must be a `SystemMessage`, never a `HumanMessage`, or the "traveller's latest message" language rule flips the reply language.
- `SupervisorIntent.plan` was hardened in gh-180 (PR #189) with a `mode="before"` validator that keeps the bare-name `Literal` list; growing that field into objects re-enters the same validator surface. That is the main reason for Standard-depth research rather than Quick.

Two implementation forks remain; both have a safe default so confidence is `medium`, not `low`:

1. **Where the per-task query lives in the structured output.** Default: add a parallel `task_queries`-style field (or `primary_query` + per-plan-step query) rather than turning `plan` entries into objects, so the gh-180 validator and every existing `plan=["concierge"]` test keep their shape. The alternative (plan entries become `{agent, query}` objects) is viable and is weighed in `research-brief.md`.
2. **Single-intent path.** Default: append the task note on both paths (single specialist and fan-out) so step 3 of the artifact (reflection sees the question) can reuse the same text; the fan-out path is where the value is. The alternative is fan-out only.

### Alternatives considered

- Replace the hand-rolled subgraphs with deepagents / `create_agent` middleware — rejected already by the MIN-61 spike (`specs/agent-middleware-spike`); middleware cannot reach the current subgraphs.
- Deliver the task as a `HumanMessage` (the blog's literal mechanism) — rejected by the recorded language-flip bug above.

### Deviations

- Task 1.1, Rule 1 — the plan's dedup test data `["a","b","c"]` contradicted its own ≥3-char fallback rule; the test uses `["query a","query b","query c"]` so it measures alignment, not the length guard. Accepted by the task reviewer; PLAN.md reconciled.
- Correctness review, Rule 1 (68aaee2) — design D2 reversed: the task note moved from a separate trailing `SystemMessage` into the end of the single leading system message (`with_task_note`). The trailing form broke the single-leading-system invariant (four existing tests went red in the full suite, which no per-task Verify ran) and crashed every routed turn on an Anthropic-configured specialist. An independent re-review confirmed the defect closed with no new findings. design.md D2 records the change and its unmeasured cache cost.
- Task 2.2, Rule 3 (controller) — `test_total_case_count_at_least_60` pins the exact golden count (`== 103`) in a file outside the task's Files set, so the implementer stopped as BLOCKED. The controller bumped it to 105, following the gh-166 precedent (28bb989). PLAN.md Task 2.2 Files now lists `tests/eval/test_datasets.py`.
- Task 1.1, Rule 3 — ruff B905 required `zip(..., strict=True)`; safe because the branch is guarded by an equal-length check.

### Advisory Findings (correctness review, below threshold 75)

Six finders over 34f9920..058e8dd; seven candidates; one independent scorer per candidate.

- 75 → fix loop — `_base.py:260` trailing task-note `SystemMessage` crashes every routed turn on an Anthropic-configured specialist and breaks the single-leading-system invariant (4 existing tests red). Fixed by folding the note into the leading system message (see Deviations).
- 50 — `_base.py:260` the trailing note lands after the reflection REVISE note, so the last instruction is the original task. Resolved by the same fold.
- 50 — `_base.py:260` the note is re-appended after the ToolMessages on every tool round. Resolved by the same fold.
- 50 — `supervisor.py:434` if the model repeats `target_agent` inside `plan`, lengths still match and `setdefault` keeps only the first slice for that agent; needs the model to break v13 ("`plan` must never contain `target_agent`"). Not fixed.
- 50 — `supervisor.py:432` `plan=null` with a one-entry `task_queries` replaces the single specialist's full message with the model's paraphrase; needs the model to ignore both the prompt and the Field description. Not fixed. A one-line guard (use `task_queries` only when more than one task is emitted) would close it.
- 25 — `supervisor.py:438` a valid 1–2 character CJK slice falls back to the whole message; the product supports `en` and `vi` only.
- 25 — `supervisor.py:430` a dropped plan entry plus a missing primary query can re-align queries to the wrong agents; needs two independent prompt violations.
- pre-existing on main, out of scope — reflection REVISE stores `SystemMessage(REFLECTION_REVISE_NOTE)` in `messages` (`nodes.py:258`), so the retry input has two system messages and still raises on an Anthropic-configured specialist. Unchanged by this branch; worth its own issue.
- prior-art finder: no recorded failure reintroduced (language flip, sync-over-async, gh-180 unhashable, active.yaml pointer, prompt-version collision).

### Minor review findings (forwarded to the final review chain)

- 1.2 — `task_note` docstring says the query sits "on its own line"; it follows a blank line (`\n\n`). Wording only.
- 1.3 — CHANGELOG entry states the `task_queries` field exists, but it lands one commit later (1.1). True at branch HEAD.
- 1.3 — v13 does not say which language wins when the current turn's language differs from the Rule 4 dominant language.
- 1.3 — ruff-format reflowed two pre-existing lines in `tests/prompts/test_supervisor_prompt.py`; no behaviour change.
- 1.4 — `ask_coverage` criteria do not define the score as the fraction of asks answered; tighten if the first judged run is noisy.
- 1.4 — `apps/api/eval/README.md` "Known gap" note already listed only four rubrics before this work (now seven); out of scope, docs sweep.
- 1.1 — repeated-agent tie-break (first `task_queries` entry wins) is a documented but unpinned choice.
- 2.2 — `test_total_case_count_at_least_60` asserts an exact count (`== 105`); its name is stale. Rename later.
- 2.2 — the two new goldens' notes do not name supervisor v13 Rule 3, which their fan-out expectation depends on (en-03/en-04 cite v10 the same way).
- 2.1 — `test_note_not_persisted` covers one assistant pass only (no tool round). The code cannot leak the note, because it is a local rebuilt per call and the node returns only the AIMessage. A tools-round variant would pin that.
- 2.1 — after a tool round a trailing SystemMessage follows the ToolMessages. OpenAI accepts it; some providers (Anthropic chat) reject a non-leading system message. Unverified portability risk, not a defect on the configured provider.
- 1.1 — fix round 1 (4788a89) closed an Important finding: a non-string `task_queries` entry raised ValidationError before the supervisor ran. Residual Minor: a tuple is dropped as a non-list; irrelevant on the JSON wire.

### Verify

All rows run from the repo root at HEAD 68aaee2, 2026-09-10 (after the correctness-review fix). The full backend suite was also run at that tree: 2413 passed, 0 failed (baseline on main: 2388 passed). A whole-suite run is not a Verify row by rule.

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| `AgentTask.query` now has a reader | `grep -rnF -e '.get("query")' -e '["query"]' -e 'task.query' apps/api/app/agents` | 0 | hit at `app/agents/state.py:251` (`task_note`). At intake the same grep exited 1 with 0 hits: the field was written but read nowhere | |
| Plan contract | `python3 .claude/scripts/check_plan_contract.py specs/specialist-task-description/PLAN.md` | 0 | 7 tasks / 3 waves, SC-1…SC-9 | |
| Distinct query per task | `.venv/bin/python -m pytest apps/api/tests/agents/test_supervisor_task_queries.py -q -k distinct` | 0 | 1 passed | SC-1 |
| Fallback to the user message | `.venv/bin/python -m pytest apps/api/tests/agents/test_supervisor_task_queries.py -q -k fallback` | 0 | 2 passed | SC-2 |
| `plan` wire schema and existing constructors unchanged | `.venv/bin/python -m pytest apps/api/tests/agents/test_supervisor_plan_semantics.py apps/api/tests/agents/test_supervisor.py -q` | 0 | 25 passed | SC-3 |
| `with_task_note` shape | `.venv/bin/python -m pytest apps/api/tests/agents/test_task_note.py -q` | 0 | 5 passed | SC-4 |
| Specialist receives the note in its one leading system message, on both paths | `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_task_note.py -q -k receives` | 0 | 2 passed | SC-5 |
| Tool result and revise note stay last; one leading system message | `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_task_note.py -q -k last` | 0 | 2 passed: `test_tool_round_keeps_tool_result_last`, `test_revise_note_stays_last` | SC-5 |
| Single-leading-system invariant (the four tests the first design broke) | `.venv/bin/python -m pytest apps/api/tests/agents/test_profile_injection.py apps/api/tests/agents/test_procedural_injection.py -q` | 0 | 5 passed; 4 of them were red at 058e8dd | SC-5 |
| Note never persisted | `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_task_note.py -q -k not_persisted` | 0 | 1 passed | SC-6 |
| Fan-out end to end: distinct notes, none checkpointed | `.venv/bin/python -m pytest apps/api/tests/agents/test_multi_intent_routing.py -q` | 0 | 8 passed; the new test fails when the note append in `_base.py` is disabled | SC-5 |
| Supervisor prompt v13 active | `.venv/bin/python -m pytest apps/api/tests/prompts/test_supervisor_prompt.py -q` | 0 | 5 passed | SC-7 |
| `ask_coverage` rubric and goldens | `.venv/bin/python -m pytest apps/api/tests/eval/test_metrics_judged.py apps/api/tests/eval/test_datasets.py -q` | 0 | 46 passed | SC-8 |
| Lint on touched paths | `.venv/bin/ruff check apps/api/app apps/api/evalkit apps/api/eval apps/api/tests/prompts apps/api/tests/agents/test_supervisor_task_queries.py apps/api/tests/agents/test_task_note.py apps/api/tests/agents/test_subagent_task_note.py apps/api/tests/agents/test_multi_intent_routing.py apps/api/tests/eval/test_metrics_judged.py apps/api/tests/eval/test_datasets.py` | 0 | All checks passed | SC-9 |

### Not auto-verified

- Lane classification — reached traceability; flags were assigned by reading the files named under Rationale, no command asserts them.
- The model actually fills `task_queries` on fan-out turns, and `ask_coverage` improves on `routing-multi-en-05` / `routing-multi-vi-01` — not run. It needs the paid judged eval (`make eval-check`, k=3, real key); the offline suite proves plumbing only.
- No routing regression from supervisor v13 against `eval/baselines/main.json` — not run, same paid gate.
- Trailing `SystemMessage` after `ToolMessage`s on a non-OpenAI provider — not verified; OpenAI is the configured provider.

### Rollback

- Whole feature: `git revert 80302ec 34e9e6b a4e26a4 4788a89 b826228 7bcb712 efde4ca f10d7fd` (newest first).
- Prompt only: set `supervisor: 12` in `apps/api/app/prompts/active.yaml`, then rebuild the graph (`docker exec api-api-1 touch app/main.py`). With v12 the model leaves `task_queries` null and every task falls back to the user message.

### Harness-Delta

- backlog: `verify_summary.py --lane` applies SC coverage as soon as PLAN.md declares an SC table, so a normal-lane spec cannot pass Check 1.6 between planning and Task 3.1 (the same state `specs/prompt-caching-system-prefix` is in today). Either the coverage check should key off PLAN `status: active`+rows-run, or the spec folder is committed together with the final task.

- backlog (corrected at planning): `hooks/risk-corroboration.sh` maps `\brole\b` to the `authorization` block gate but only scans code (`:!*.md`), so `supervisor/v13.md`'s `# Role:` heading is safe; the constraint moves to added `.py` lines (the new `Field(description=...)` must not use the word). Recorded in PLAN.md Global Constraints.
