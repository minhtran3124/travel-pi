# specialist-task-description — Summary

Lane: normal
Confidence: medium
Reason: No manifest hard gate fires (no auth, migration, route, provider or high-blast file); two flags fire — existing-behavior (every specialist turn's model input changes and SupervisorIntent's structured output grows a per-task query) and weak-proof (the behaviour is prompt-driven; offline tests can pin the plumbing but the value claim needs a judged eval golden), and the diff spans >2 files — so normal, not tiny.
Flags: existing-behavior, weak-proof
Affects: agent supervisor structured output (`SupervisorIntent`/`AgentTask.query`), specialist input assembly (`subagents/_base.py`), fan-out worker (`synthesis_worker.py`), supervisor prompt (unchanged at v12; a v13 was built and reverted, E003), eval rubric + goldens (`eval/datasets/routing.json`)
Input-type: change request
Route: using-git-worktrees → xia2 (Standard) → writing-plans → subagent-driven-development
Escalate: no at intake (notify-and-proceed with documented defaults); during review three human decisions were recorded, E001–E003 in ESCALATIONS.md

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

A fanned-out specialist can now receive its own slice of the traveller's message. `SupervisorIntent` gains a `task_queries` field; its schema description tells the model to write one self-contained query per specialist in `[target_agent, *plan]` order, and the model fills it from that description alone (supervisor prompt unchanged at v12). When two or more tasks are emitted and the list aligns, each `AgentTask.query` carries that specialist's slice; otherwise, and always for a single task, it is the traveller's whole message. Malformed entries are coerced instead of failing the turn. `with_task_note` folds the slice into the end of the specialist's single leading system message behind `TASK_NOTE_PREAMBLE`, only when the query differs from the traveller's own sentence, so single-intent turns send the same model input as before. On the fan-out path `synthesis_worker` hands the task over through the declared `tasks` key. Two fan-out goldens and a judged `ask_coverage` rubric were added; the judged eval shows no measurable gain over main yet (see Eval results). A supervisor prompt v13 was built and reverted after it regressed routing.

### Rationale

Intake facts that fix the lane (all read from the tree at 34f9920):

- `app/agents/supervisor.py:368-378` builds every `AgentTask` with `query=last_user_message` — the same full user sentence for all N tasks. `AgentTask.query` (`app/agents/schemas.py:21`) already exists and is documented as "the user-facing request specific to this specialist", but no consumer reads it: grep `\.get("query")|\["query"\]|task\.query` over `app/agents` → 0 hits outside the constructor.
- `app/agents/subagents/_base.py` `assistant()` invokes `[system_msg, *state["messages"]]` — the full-history fork the blog describes, with no task text. `synthesis_worker.py` deep-copies the same history into each parallel worker and sets `inner_state["task"]`, which the inner subgraph likewise never reads.
- The delivery channel is already decided by a recorded failure: `docs/solutions/agent/reflection-humanmessage-language-flip.md` (critical) — internal steering text must be a `SystemMessage`, never a `HumanMessage`, or the "traveller's latest message" language rule flips the reply language.
- `SupervisorIntent.plan` was hardened in gh-180 (PR #189) with a `mode="before"` validator that keeps the bare-name `Literal` list; growing that field into objects re-enters the same validator surface. That is the main reason for Standard-depth research rather than Quick.

Two implementation forks remain; both have a safe default so confidence is `medium`, not `low`:

1. **Where the per-task query lives in the structured output.** Default: add a parallel `task_queries`-style field (or `primary_query` + per-plan-step query) rather than turning `plan` entries into objects, so the gh-180 validator and every existing `plan=["concierge"]` test keep their shape. The alternative (plan entries become `{agent, query}` objects) is viable and is weighed in `research-brief.md`.
2. **Single-intent path.** (Superseded by E001-A: the note is added only when the supervisor actually split the message.) Original default: append the task note on both paths (single specialist and fan-out) so step 3 of the artifact (reflection sees the question) can reuse the same text; the fan-out path is where the value is. The alternative is fan-out only.

### Alternatives considered

- Replace the hand-rolled subgraphs with deepagents / `create_agent` middleware — rejected already by the MIN-61 spike (`specs/agent-middleware-spike`); middleware cannot reach the current subgraphs.
- Deliver the task as a `HumanMessage` (the blog's literal mechanism) — rejected by the recorded language-flip bug above.

### Deviations

- Task 1.1, Rule 1 — the plan's dedup test data `["a","b","c"]` contradicted its own ≥3-char fallback rule; the test uses `["query a","query b","query c"]` so it measures alignment, not the length guard. Accepted by the task reviewer; PLAN.md reconciled.
- Decision E003-A (f71dc96) — Task 1.3 undone: supervisor v13 reverted to v12 (active.yaml, CHANGELOG and the prompt test back to main; v13.md deleted) after the eval and probe showed it dropping the budget+concierge fan-out 6/18 vs 0/30.
- Live-evidence promotion (3de9993) — correctness advisory at score 50 (`plan=null` + one `task_queries` entry replaces the single specialist's message) fixed: the probe saw the model fill the field for a single booking request 6/6 under v12. `task_queries` now applies only with two or more tasks.
- Intent review, decision E001-A (f3cc9f5, 1101c01) — design D3 narrowed: the note is added only when the task query differs from the traveller's own sentence, so single-intent turns and fan-out fallbacks send the same model input as before this feature. Decided by the user in session.
- Correctness review, Rule 1 (68aaee2) — design D2 reversed: the task note moved from a separate trailing `SystemMessage` into the end of the single leading system message (`with_task_note`). The trailing form broke the single-leading-system invariant (four existing tests went red in the full suite, which no per-task Verify ran) and crashed every routed turn on an Anthropic-configured specialist. An independent re-review confirmed the defect closed with no new findings. design.md D2 records the change and its unmeasured cache cost.
- Task 2.2, Rule 3 (controller) — `test_total_case_count_at_least_60` pins the exact golden count (`== 103`) in a file outside the task's Files set, so the implementer stopped as BLOCKED. The controller bumped it to 105, following the gh-166 precedent (28bb989). PLAN.md Task 2.2 Files now lists `tests/eval/test_datasets.py`.
- Task 1.1, Rule 3 — ruff B905 required `zip(..., strict=True)`; safe because the branch is guarded by an equal-length check.

### Advisory Findings (correctness review, below threshold 75)

Six finders over 34f9920..058e8dd; seven candidates; one independent scorer per candidate.

- 75 → fix loop — `_base.py:260` trailing task-note `SystemMessage` crashes every routed turn on an Anthropic-configured specialist and breaks the single-leading-system invariant (4 existing tests red). Fixed by folding the note into the leading system message (see Deviations).
- 50 — `_base.py:260` the trailing note lands after the reflection REVISE note, so the last instruction is the original task. Resolved by the same fold.
- 50 — `_base.py:260` the note is re-appended after the ToolMessages on every tool round. Resolved by the same fold.
- 50 — `supervisor.py:434` if the model repeats `target_agent` inside `plan`, lengths still match and `setdefault` keeps only the first slice for that agent; needs the model to break the same rule in the shipped v12 (`supervisor/v12.md:130`, "`plan` must **never** contain `target_agent`"); re-graded after E003, unchanged. Not fixed.
- 50 → fixed (3de9993) — `supervisor.py:432` `plan=null` with a one-entry `task_queries` replaced the single specialist's full message with the model's paraphrase. The supervisor probe then saw it happen 6/6 on a single booking request under v12, so it was promoted and fixed: `task_queries` applies only with two or more tasks.
- 25 — `supervisor.py:438` a valid 1–2 character CJK slice falls back to the whole message; the product supports `en` and `vi` only.
- 25 — `supervisor.py:430` a dropped plan entry plus a missing primary query can re-align queries to the wrong agents; needs two independent prompt violations.
- pre-existing on main, out of scope — reflection REVISE stores `SystemMessage(REFLECTION_REVISE_NOTE)` in `messages` (`nodes.py:258`), so the retry input has two system messages and still raises on an Anthropic-configured specialist. Unchanged by this branch; worth its own issue.
- prior-art finder: no recorded failure reintroduced (language flip, sync-over-async, gh-180 unhashable, active.yaml pointer, prompt-version collision).

### Intent Findings (intent-review over 34f9920..21dcb41, plan-blind)

- 1 — drift, behaviorally different — single-intent turns copied the user's sentence into the system prompt as the task ("thay vì copy nguyên câu user"). Escalated as E001; user chose A; fixed in f3cc9f5.
- 2 — drift, allowed by the intent — the note is folded into the leading system message rather than appended at the end of the input; the intent's gotcha paragraph allows "ghép vào system prompt". Advisory: recency is weaker at the start of the input than at the end.
- 3 — gap, ambiguous — "Cần thêm golden multi-intent để đo": goldens and rubric added, effect not measured. Escalated as E002; user chose A (run the judged eval before the PR); results under Eval results.
- 4 — excess (size) — the intent estimated "2 file"; the diff touches 5 app modules, a new prompt version, an eval rubric, a dataset and 7 test files. Report-only; the growth serves the per-task query, fan-out hand-off and measurement clauses.
- 5 — excess — the `ask_coverage` rubric in evalkit and the `_coerce_task_queries` validator were not asked for (the validator closes a review-found crash). Report-only.

### Intent Findings — round 2 (intent-review over 34f9920..f71dc96, with E001–E003 as oracle)

- 1, 2, 5 — drift allowed by the user's decisions: split only on fan-out (E001), the field description instead of a prompt section (E003), the note folded into the system prompt (the intent's own alternative). No action.
- 3 — benefit not demonstrated; SUMMARY states it, and the Eval reading now names the closest-to-shipped `routing-multi-en-05` drop (0.79 → 0.54, one sample). Report-only; the PR must say so (E003).
- 4 — the goldens measure a 2-worker fan-out only, while the intent speaks of 3 workers. Backlog with E003's larger-eval follow-up.
- 6 — size beyond the "2 file" estimate; every extra piece serves a clause. Report-only.
- 7 — stale SUMMARY lines after E001/E003 (Affects, Escalate, Fork 2, the `supervisor.py:434` residual). Fixed in this commit; STATE.md refreshed.

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

All rows run from the repo root at HEAD f71dc96, 2026-09-10 (after the correctness-review fix, E001, the single-task guard and the E003 revert). The full backend suite at 68aaee2: 2413 passed, 0 failed (baseline on main: 2388 passed); at 1101c01: 2418 passed; at f71dc96 (shipped code): 2419 passed, 0 failed. A whole-suite run is not a Verify row by rule.

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| `AgentTask.query` now has a reader | `grep -rnF -e '.get("query")' -e '["query"]' -e 'task.query' apps/api/app/agents` | 0 | hit at `app/agents/state.py:251` (`task_note`). At intake the same grep exited 1 with 0 hits: the field was written but read nowhere | |
| Plan contract | `python3 .claude/scripts/check_plan_contract.py specs/specialist-task-description/PLAN.md` | 0 | 7 tasks / 3 waves, SC-1…SC-9 | |
| Distinct query per task | `.venv/bin/python -m pytest apps/api/tests/agents/test_supervisor_task_queries.py -q -k distinct` | 0 | 1 passed | SC-1 |
| Fallback to the user message | `.venv/bin/python -m pytest apps/api/tests/agents/test_supervisor_task_queries.py -q -k fallback` | 0 | 2 passed | SC-2 |
| `plan` wire schema and existing constructors unchanged | `.venv/bin/python -m pytest apps/api/tests/agents/test_supervisor_plan_semantics.py apps/api/tests/agents/test_supervisor.py -q` | 0 | 25 passed | SC-3 |
| `with_task_note` shape | `.venv/bin/python -m pytest apps/api/tests/agents/test_task_note.py -q` | 0 | 9 passed | SC-4 |
| Specialist receives the note in its one leading system message, on both paths | `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_task_note.py -q -k receives` | 0 | 2 passed | SC-5 |
| Same-sentence task gets no note (E001) | `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_task_note.py -q -k same_sentence` | 0 | 1 passed | SC-5 |
| Tool result and revise note stay last; one leading system message | `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_task_note.py -q -k last` | 0 | 2 passed: `test_tool_round_keeps_tool_result_last`, `test_revise_note_stays_last` | SC-5 |
| Single-leading-system invariant (the four tests the first design broke) | `.venv/bin/python -m pytest apps/api/tests/agents/test_profile_injection.py apps/api/tests/agents/test_procedural_injection.py -q` | 0 | 5 passed; 4 of them were red at 058e8dd | SC-5 |
| Note never persisted | `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_task_note.py -q -k not_persisted` | 0 | 1 passed | SC-6 |
| Fan-out end to end: distinct notes, none checkpointed | `.venv/bin/python -m pytest apps/api/tests/agents/test_multi_intent_routing.py -q` | 0 | 8 passed; the new test fails when the note append in `_base.py` is disabled | SC-5 |
| Supervisor stays at v12; `task_queries` on the wire (E003) | `.venv/bin/python -m pytest apps/api/tests/prompts/test_supervisor_prompt.py apps/api/tests/agents/test_supervisor_task_queries.py -q` | 0 | 18 passed | SC-7 |
| `ask_coverage` rubric and goldens | `.venv/bin/python -m pytest apps/api/tests/eval/test_metrics_judged.py apps/api/tests/eval/test_datasets.py -q` | 0 | 46 passed | SC-8 |
| Lint on touched paths | `.venv/bin/ruff check apps/api/app apps/api/evalkit apps/api/eval apps/api/tests/prompts apps/api/tests/agents/test_supervisor_task_queries.py apps/api/tests/agents/test_task_note.py apps/api/tests/agents/test_subagent_task_note.py apps/api/tests/agents/test_multi_intent_routing.py apps/api/tests/eval/test_metrics_judged.py apps/api/tests/eval/test_datasets.py` | 0 | All checks passed | SC-9 |

### Eval results (decision E002-A, 2026-09-10, `gpt-5.4-mini`, judge k=3, one agent sample per golden)

All runs in one-off `api-api` containers (the dev container mounts main); reports are gitignored under `apps/api/eval/reports/sttd-*.json`.

| Run | Agent code | Supervisor prompt | Scope | Result |
| --- | --- | --- | --- | --- |
| v13 full | branch 1101c01 | v13 | full suite (87) | 70/87 (80.5%); `eval-compare` vs `eval/baselines/main.json` (67/84, gh-153 era) exit 1: dates, language, journal below tolerance |
| v12+field | branch 1101c01 | v12 pinned | routing (19) | 18/19 |
| main | main 34f9920 + branch eval/evalkit | v12 (active) | routing (19) | 18/19 |

| Golden | main | v12+field | v13 |
| --- | --- | --- | --- |
| `routing-multi-en-05` ask_coverage | 0.79 pass | 0.54 fail | 0.70 pass |
| `routing-multi-vi-01` ask_coverage | 0.79 pass | 0.92 pass | 0.81 pass |
| `routing-multi-en-03` fan-out | pass | pass | fail (budget+planner) |

Supervisor-only probe (same model and DB context as the eval), `routing-multi-en-03`, budget+concierge fan-out rate: main 12/12; branch v12+field 18/18 (6+12); branch v13 12/18 (6 times it dropped concierge). Under v12 the model still fills `task_queries` from the schema description alone (12/12 real splits on that input), so "v12+field" is not a no-feature baseline — `main` is. Other v13 regressions against the stale baseline (`dates-multi_turn-en-01`, `language-ambiguous-*`, `flight_search-multi_turn-en-01`, `journal-happy-en-02`) show the same distribution under v12 in the probe, or fail on main-identical specialist input, or are tracked issues (#148, #182).

Reading: no measurable ask-coverage gain over main. Main already covers both asks at 0.79. The configuration closest to what ships (`v12+field`) scored `routing-multi-en-05` at 0.54 and FAILED it, and scored `routing-multi-vi-01` at 0.92; each is one agent sample, so neither the drop nor the rise is established. The v13 prompt section causes a measured routing regression. The single-intent paraphrase risk seen under v12 (6/6 on a single booking request) is closed by 3de9993.

### Not auto-verified

- Lane classification — reached traceability; flags were assigned by reading the files named under Rationale, no command asserts them.
- A benefit from the task note — not demonstrated. The judged eval (one agent sample per golden) shows main already at 0.79 ask_coverage on both fan-out goldens and the branch scattering 0.54–0.92; a claim needs several agent samples per golden and more fan-out goldens.
- The final shipped configuration (supervisor v12 + field + single-task guard, HEAD f71dc96) was not re-run through the judged eval; the closest run is `v12+field` at 1101c01, which lacks only the guard (single-task turns only).
- Trailing `SystemMessage` after `ToolMessage`s on a non-OpenAI provider — not verified; OpenAI is the configured provider.

### Rollback

- Whole feature: `git revert` every commit in `main..feat/specialist-task-description` newest first, or close the PR unmerged. There is no schema, migration or prompt-version change left to undo: the supervisor prompt is unchanged at v12.
- Behaviour only, without a revert: the task note is inert when `task_queries` is null, so removing the field's description from `SupervisorIntent` returns every turn to main's model input.

### Harness-Delta

- backlog: `verify_summary.py --lane` applies SC coverage as soon as PLAN.md declares an SC table, so a normal-lane spec cannot pass Check 1.6 between planning and Task 3.1 (the same state `specs/prompt-caching-system-prefix` is in today). Either the coverage check should key off PLAN `status: active`+rows-run, or the spec folder is committed together with the final task.

- backlog (corrected at planning): `hooks/risk-corroboration.sh` maps `\brole\b` to the `authorization` block gate but only scans code (`:!*.md`), so `supervisor/v13.md`'s `# Role:` heading is safe; the constraint moves to added `.py` lines (the new `Field(description=...)` must not use the word). Recorded in PLAN.md Global Constraints.
