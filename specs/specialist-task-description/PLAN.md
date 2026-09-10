---
slug: specialist-task-description
status: active
owner: minhtran3124
created: 2026-09-10
---

# Fork with a task description for every specialist

## 1. Motivation

`app/agents/supervisor.py` writes one `AgentTask` per specialist but gives every task the same
`query` (the whole user sentence), and nothing reads `AgentTask.query`. `_base.py` forks the full
history into each specialist with no statement of that specialist's slice, so on a fan-out turn
each worker guesses its share. Step 2 of the *Fork hay Isolated* review (see
`research-brief.md`, `design.md` D1–D3) closes that gap: the supervisor emits a per-task query and
every specialist receives it as a trailing `SystemMessage` behind a fixed preamble.

## 2. Non-goals

- Reflection seeing the question (step 3 of the review) — separate spec.
- Prompt caching / retention (step 1) — `specs/prompt-caching-system-prefix`.
- Changing `plan`'s wire schema, `synthesize`, `synthesis_worker` state propagation, or any
  specialist's own prompt.
- Running the paid judged eval inside a task `Verify` — it is a manual pre-merge gate.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | With `task_queries` present, each emitted task carries its own query, aligned to `[target, *plan]` | `.venv/bin/python -m pytest apps/api/tests/agents/test_supervisor_task_queries.py -q -k distinct` | exit 0 |
| SC-2 | A missing, short, or blank `task_queries` entry falls back to the last user message for that task | `.venv/bin/python -m pytest apps/api/tests/agents/test_supervisor_task_queries.py -q -k fallback` | exit 0 |
| SC-3 | The `plan` wire schema and every existing `SupervisorIntent(...)` constructor are unchanged | `.venv/bin/python -m pytest apps/api/tests/agents/test_supervisor_plan_semantics.py apps/api/tests/agents/test_supervisor.py -q` | exit 0 |
| SC-4 | `task_note(state)` returns a `SystemMessage` starting with `TASK_NOTE_PREAMBLE` and ending with the task query; returns `None` when no task or query is present | `.venv/bin/python -m pytest apps/api/tests/agents/test_task_note.py -q` | exit 0 |
| SC-5 | The last message a specialist model receives is that `SystemMessage`, on both the single-intent path (`tasks[0]` from the supervisor) and the fan-out path (`tasks=[task]` set by `synthesis_worker`) | `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_task_note.py -q -k receives` | exit 0 |
| SC-6 | The task note is never written to `state["messages"]` (no returned or checkpointed message is a `SystemMessage` whose content starts with `TASK_NOTE_PREAMBLE`) | `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_task_note.py -q -k not_persisted` | exit 0 |
| SC-7 | Supervisor prompt v13 is active and tells the model to write one query per specialist in the traveller's language | `.venv/bin/python -m pytest apps/api/tests/prompts/test_supervisor_prompt.py -q` | exit 0 |
| SC-8 | Judged rubric `ask_coverage` is registered as data and two `routing-multi-*` goldens declare `tasks_expected` + `ask_coverage` | `.venv/bin/python -m pytest apps/api/tests/eval/test_metrics_judged.py apps/api/tests/eval/test_datasets.py -q` | exit 0 |
| SC-9 | Lint is clean on every touched path (the branch carries 7 pre-existing ruff errors in untouched test files, so the whole `tests/` tree is out of scope) | `.venv/bin/ruff check apps/api/app apps/api/evalkit apps/api/eval apps/api/tests/prompts apps/api/tests/agents/test_supervisor_task_queries.py apps/api/tests/agents/test_task_note.py apps/api/tests/agents/test_subagent_task_note.py apps/api/tests/agents/test_multi_intent_routing.py apps/api/tests/eval/test_metrics_judged.py apps/api/tests/eval/test_datasets.py` | exit 0 |

All checks run from the repo root — `verify_summary.py --lane` re-runs every row with `cwd=repo_root`, where `../../.venv` does not resolve.

## Global Constraints

- Internal steering text is a `SystemMessage`, never a `HumanMessage`
  (`docs/solutions/agent/reflection-humanmessage-language-flip.md`).
- `SupervisorIntent.plan` keeps its `list[Literal[...]] | None` wire schema; the new field is
  additive with default `None` so the 8 existing `SupervisorIntent(...)` test constructors stay
  valid.
- No new key on `TravelAgentState`; the task note is built inside `assistant()` at invoke time
  and never returned in `{"messages": [...]}`. A compiled subgraph drops input keys its schema
  does not declare (verified 2026-09-10: `task` arrives as `None`, `tasks` arrives intact), so the
  fan-out path must hand the task to the specialist through the declared `tasks` key.
- New prompt = new file `app/prompts/supervisor/v13.md` (copy of v12 + delta) + `active.yaml`
  bump + `CHANGELOG.md` entry; never edit `v12.md`.
- Added `.py` lines must not contain the bare word `role` (the `authorization` gate in
  `hooks/risk-corroboration.sh` matches `\brole\b` in code; `*.md` is excluded).
- Every `Verify` and SC check is one pipe-free command under 60 s, written to run from the
  repo root (`.venv/bin/python -m pytest apps/api/tests/...`) because `verify_summary.py`
  executes rows with `cwd=repo_root`; the whole suite runs only at `finishing-a-development-branch`.
- Same-wave tasks share no file.

## 4. Tasks

### Task 1.1 — Supervisor emits a per-task query (wave 1)

- **Files:** app/agents/supervisor.py, tests/agents/test_supervisor_task_queries.py
- **Action:** Write the test file first. Add `task_queries: list[str] | None = Field(default=None, description=...)` to `SupervisorIntent` — the description says: one entry per specialist in `[target_agent, *plan]` order, each a self-contained restatement of that specialist's slice of THIS message in the traveller's language, no invented details, null for the single-specialist case. Do not use the word "role" in the description. In `supervisor()`, after `task_agents` is built, take `getattr(intent, "task_queries", None) or []`, and for each `idx, agent` use `queries[idx].strip()` when it exists and is at least 3 characters, else `last_user_message`. Alignment rule: `_coerce_plan` (a `mode="before"` validator) already drops `booking`/unknown/nested entries before `supervisor()` sees `raw_plan`, and the dedup loop drops more, so positions shift. Build `{agent: query}` from `zip([target, *candidates], queries)` ONLY when `len(queries) == len([target, *candidates])`; when the lengths differ, fall back to `last_user_message` for every task (a mis-aligned non-blank query is worse than no query). Look up each emitted task's query by agent name, so `MAX_LEDGER_STEPS` truncation and dedup stay safe. Keep the `AgentTask(...)` construction otherwise unchanged. Tests (FakeLLM `structured_responses`): `test_distinct_query_per_task` (planner+concierge with two queries → two different `query` values in order); `test_fallback_when_task_queries_missing` (field `None` → both tasks carry the user message); `test_fallback_when_entry_blank_or_short` (`["find flights", " "]` → second task carries the user message); `test_alignment_survives_plan_dedup` (`plan=["planner","concierge"]`, target planner, queries `["query a","query b","query c"]` → concierge gets `"query c"`; one-letter strings would trip the ≥3-char fallback); `test_length_mismatch_falls_back_for_all` (`plan=["concierge"]`, queries `["only one"]` → both tasks carry the user message).
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/agents/test_supervisor_task_queries.py apps/api/tests/agents/test_supervisor_plan_semantics.py apps/api/tests/agents/test_supervisor.py -q`
- **Done:** The four new tests pass; `test_wire_schema_keeps_plan_enum` passes unchanged; `test_supervisor_emits_single_task` passes unchanged (a `None` field keeps `query == "plan my trip"`).
- **Criteria:** SC-1, SC-2, SC-3
- **Interfaces:** Consumes the existing AgentTask model in app/agents/schemas.py (unchanged). Produces `SupervisorIntent.task_queries` in `app/agents/supervisor.py` and per-task `AgentTask.query` values in `state["tasks"]`.

### Task 1.2 — `task_note` helper and preamble constant (wave 1)

- **Files:** app/agents/state.py, app/agents/constants.py, tests/agents/test_task_note.py
- **Action:** Write the test file first. In `constants.py` add `TASK_NOTE_PREAMBLE` next to `REFLECTION_REVISE_NOTE`, modelled on deepagents' fork preamble but addressed as an internal note: the messages above are the conversation so far; this is an internal routing note, not a message from the traveller; use the facts, dates and identifiers already established above and do not answer generically; keep replying in the traveller's own language; your task for this turn is below. End with a blank line. In `state.py` add `def task_note(state: TravelAgentState) -> SystemMessage | None` beside `with_reply_language`: read `(state.get("tasks") or [None])[0]` only — never an undeclared `task` key, which a compiled subgraph drops (Global Constraints); return `None` when there is no task or `query` is blank; else `SystemMessage(content=TASK_NOTE_PREAMBLE + query)`. Docstring in the existing style (`:param`/`:return`). Tests: `test_reads_first_task`, `test_ignores_undeclared_task_key` (state with only `task` → `None`), `test_none_without_tasks`, `test_none_on_blank_query`, `test_content_starts_with_preamble_and_ends_with_query`, `test_is_system_message_not_human`.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/agents/test_task_note.py apps/api/tests/agents/test_state.py -q`
- **Done:** Six new tests pass; `tests/agents/test_state.py` passes unchanged; `grep -c "^TASK_NOTE_PREAMBLE" apps/api/app/agents/constants.py` prints 1.
- **Criteria:** SC-4
- **Interfaces:** Consumes the tasks list written to state by Task 1.1 (single-intent) and by Task 2.1's worker (fan-out). Produces `task_note()` in `app/agents/state.py` and `TASK_NOTE_PREAMBLE` in `app/agents/constants.py`.

### Task 1.3 — Supervisor prompt v13 teaches the per-task query (wave 1)

- **Files:** app/prompts/supervisor/v13.md, app/prompts/active.yaml, app/prompts/CHANGELOG.md, tests/prompts/test_supervisor_prompt.py
- **Action:** Copy `v12.md` to `v13.md` verbatim, then add under "## Multi-step Plan" (after the "Keep it short" bullet) a subsection "### Task queries" stating: when `plan` is non-empty, also fill `task_queries` with one entry per specialist in `[target_agent, *plan]` order; each entry restates only that specialist's part of THIS message, self-contained, in the traveller's language, copying names, dates and counts the traveller wrote and inventing nothing; leave `task_queries` null when `plan` is null. Extend the worked example paragraph (the "Worked example — …" prose at the end of the section, NOT a new `- "plan my weekend` bullet — `test_supervisor_prompt_has_contrastive_pair` counts lines with that prefix): `task_queries = ["find me flights to Tokyo", "what visa do I need for Tokyo?"]`. Keep the `# Role: Supervisor` heading as-is: the `authorization` gate scans code only, `*.md` is excluded. Bump `active.yaml` `supervisor: 13`. Prepend a `## specialist-task-description — supervisor v13: one query per fanned-out specialist` entry to `CHANGELOG.md` in the existing style, naming the pinning test. Add to `tests/prompts/test_supervisor_prompt.py`: `test_supervisor_prompt_explains_task_queries` asserting the active prompt contains `task_queries`, `[target_agent, *plan]` order wording, and the visa example line; keep the existing tests green (they read the active version).
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/prompts/test_supervisor_prompt.py -q`
- **Done:** `registry.get("supervisor")` returns v13 text containing `task_queries`; all tests in the file pass; `v12.md` is byte-identical to `main` (`git diff --quiet main -- apps/api/app/prompts/supervisor/v12.md` exits 0).
- **Criteria:** SC-7
- **Interfaces:** Consumes the task_queries field name fixed by this plan (no wave dependency on Task 1.1). Produces `app/prompts/supervisor/v13.md` and the `supervisor: 13` line in `app/prompts/active.yaml`.

### Task 1.4 — Judged rubric `ask_coverage` (wave 1)

- **Files:** evalkit/metrics/judged.py, tests/eval/test_metrics_judged.py, tests/eval/test_datasets.py
- **Action:** Add a seventh `RUBRICS` entry `ask_coverage` with `evaluation_params: _IO` and `DEFAULT_THRESHOLD`: the input may contain more than one distinct ask (for example a flight search AND a visa question); score how many of the distinct asks the actual output addresses with substance; an answer that covers every ask passes even when brief; penalize an answer that silently drops one ask or only promises to look into it; do NOT judge formatting or language. Update the module docstring count and every pin of the count: `ALL_RUBRIC_NAMES` in `tests/eval/test_metrics_judged.py` (the real pin), `test_all_six_rubrics_are_data`, `test_all_six_metrics_are_registered_by_module_import`, `test_make_all_judged_metrics_returns_all_six` (rename to `seven`), and `test_other_rubrics_do_not_request_retrieval_context`; also add `ask_coverage` to the hardcoded `judged_metrics` set in `tests/eval/test_datasets.py` (the smoke-suite guard is silently weakened without it).
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/eval/test_metrics_judged.py apps/api/tests/eval/test_datasets.py -q`
- **Done:** `cd apps/api && ../../.venv/bin/python -c "from evalkit.metrics.judged import RUBRICS; assert 'ask_coverage' in RUBRICS and len(RUBRICS) == 7"` exits 0; the test file passes.
- **Criteria:** SC-8
- **Interfaces:** Consumes nothing from other tasks. Produces the `ask_coverage` key in `evalkit/metrics/judged.py` and the widened `judged_metrics` guard in `tests/eval/test_datasets.py` for Task 2.2's goldens.

### Task 2.1 — Specialists receive the task note (wave 2)

- **Files:** app/agents/subagents/_base.py, app/agents/subagents/synthesis_worker.py, tests/agents/test_subagent_task_note.py
- **Action:** Write the test file first. In `_base.py::assistant`, after `system_msg` is built, call `note = task_note(state)` and invoke `bound.invoke([system_msg, *state["messages"], note] if note else [system_msg, *state["messages"]])`. Import `task_note` from `app.agents.state` in the same edit as its use (the ruff-on-edit hook strips an unused import). Add a comment: built per invoke and never returned in `messages`, so it is not checkpointed or replayed. In `synthesis_worker.py::worker`, next to `inner_state["task"] = task`, add `inner_state["tasks"] = [task]` with a comment that the inner subgraph drops undeclared keys, so the specialist reads its slice from the declared `tasks` key (`_replace_tasks` is last-write-wins, so the worker's single-task list replaces the parent's full list inside the inner run only; the worker never propagates `tasks` back). Tests use a `CapturingFakeLLM(FakeLLM)` defined in the test file whose `_generate` appends the received `messages` list to `self.seen` before delegating to `super()`. Build one specialist via `build_planner(lambda hint=None: llm)` and drive it with `asyncio.run(graph.ainvoke(...))`: `test_single_intent_receives_note` (state has `tasks=[{agent: planner, query: "find flights to Tokyo", index: 0}]` → last received message is a `SystemMessage` whose content starts with `TASK_NOTE_PREAMBLE` and ends with the query); `test_fan_out_receives_note` (drive `build_synthesis_worker(lambda name, hint=None: llm)` as a bare async node with `state={"task": {...}, "messages": [...], ...}` and a stub `runtime` — the specialist under it must receive the note; this is the path a real `Send` takes); `test_note_not_persisted` (no message in the result starts with `TASK_NOTE_PREAMBLE`); `test_no_task_no_note` (no task keys → last received message is the `HumanMessage`).
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/agents/test_subagent_task_note.py apps/api/tests/agents/test_subagents.py apps/api/tests/agents/test_multi_intent_routing.py apps/api/tests/agents/test_specialist_metadata_end_to_end.py -q`
- **Done:** Four new tests pass; `test_subagents.py`, `test_multi_intent_routing.py` and `test_specialist_metadata_end_to_end.py` pass unchanged.
- **Criteria:** SC-5, SC-6
- **Interfaces:** Consumes `task_note()` from Task 1.2. Produces the note-bearing model input in `app/agents/subagents/_base.py` for all five specialists and the `tasks=[task]` hand-off in `app/agents/subagents/synthesis_worker.py`.

### Task 2.2 — Two fan-out goldens measure ask coverage (wave 2)

- **Files:** eval/datasets/routing.json, tests/eval/test_datasets.py
- **Action:** Append two `suite: "full"` goldens: `routing-multi-en-05` — input "Find me flights from Hanoi to Tokyo next month, and separately what visa do I need as a Vietnamese citizen?", `expected_tasks: ["planner", "concierge"]`, `metrics: ["tasks_expected", "ask_coverage", "reply_language"]`; `routing-multi-vi-01` — input "Tìm giúp tôi chuyến bay từ Hà Nội đi Tokyo tháng sau, và cho tôi hỏi riêng người Việt cần visa gì?", same `expected_tasks` and metrics, `language: "vi"`. `notes` must say the case measures per-task query delivery (specs/specialist-task-description) and that `ask_coverage` is judged. No `expected_flow` on either (fan-out ends in `synthesize`).
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/eval/test_datasets.py -q`
- **Done:** `cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m eval --suite full --dry-run` lists both ids; `test_multi_intent_goldens_declare_tasks_expected` and `test_smoke_suite_never_declares_a_judged_metric` pass.
- **Criteria:** SC-8
- **Interfaces:** Consumes the `ask_coverage` rubric name from Task 1.4. Produces two golden entries in `eval/datasets/routing.json`.

### Task 3.1 — End-to-end fan-out turn and evidence (wave 3)

- **Files:** tests/agents/test_multi_intent_routing.py, specs/specialist-task-description/SUMMARY.md
- **Action:** Add `test_fan_out_workers_receive_distinct_task_notes`: build the graph with `_build(...)` using a capturing main FakeLLM (reuse the `CapturingFakeLLM` pattern from Task 2.1 inline; do not import from another test module) and a `SupervisorIntent(target_agent="planner", plan=["concierge"], task_queries=["find flights", "check visa"])`; after the turn, assert the set of trailing `SystemMessage` contents seen by the model includes one ending in "find flights" and one ending in "check visa", and that no message in the checkpointed thread starts with `TASK_NOTE_PREAMBLE` (a plain "no `SystemMessage`" assertion is false whenever reflection returns REVISE — `REFLECTION_REVISE_NOTE` is stored in `messages` by design, see `test_reflection_revise_after_synthesis_re_enters_synthesize`). Then fill SUMMARY `### Verify` with one row per SC actually run (command, exit, `Criterion`), `### Not auto-verified` naming the judged `ask_coverage` run if it was not executed, and `### Rollback` = `git revert <sha>` per commit.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/agents/test_multi_intent_routing.py -q`
- **Done:** The new test passes; `python3 .claude/scripts/verify_summary.py --lane specialist-task-description` (repo root) exits 0 with every SC-1…SC-9 referenced by a passing row.
- **Criteria:** SC-5, SC-6
- **Interfaces:** Consumes Task 1.1's field, Task 2.1's note delivery in `app/agents/subagents/_base.py`, and the `tasks=[task]` hand-off in `app/agents/subagents/synthesis_worker.py`. Produces the e2e test in `tests/agents/test_multi_intent_routing.py` and the evidence block in `specs/specialist-task-description/SUMMARY.md`.

## 5. Risks

- **Model under-fills `task_queries`.** Fallback to the user message keeps today's behaviour; the judged run (`make eval-check`, k=3, paid) on `routing-multi-en-05` / `-vi-01` decides whether the field is filled in practice. If both goldens score `ask_coverage` below threshold, revisit D1 (object shape) before merging.
- **Routing regression from v13.** Any prompt edit can move `plan` decisions (gh-149 / gh-173 area). Run `make eval-check` and compare `routing` against `eval/baselines/main.json`; the gate fails on a drop > 0.05.
- **Trailing `SystemMessage` after `ToolMessage`s.** Already exercised by `REFLECTION_REVISE_NOTE` on the OpenAI path; not verified on the Anthropic path (not the configured provider).
- **Reflection REVISE re-entry.** The specialist rebuilds the note on re-entry; because it is never stored, the checkpoint stays clean. Task 3.1's checkpoint assertion pins this.
- **Rubric count tests.** `ALL_RUBRIC_NAMES` and three tests pin "six" rubrics; Task 1.4 updates them — a missed one fails SC-8 loudly, not silently.
- **Query mis-alignment after dropped plan entries.** The validator and the dedup loop remove entries before tasks are built; aligning by position would steer the concierge with the booking query. Mitigated by the length-equality rule in Task 1.1 (fall back for all on mismatch) and by name lookup, which also makes `MAX_LEDGER_STEPS` truncation safe.

## 6. Status Log

- 2026-09-10 — task 3.1 complete; commit 80302ec. Controller ran SC-1…SC-9 at HEAD 80302ec (all exit 0) and recorded them in SUMMARY; `verify_summary --lane` and `--check` pass. Next: final review chain.
- 2026-09-10 — tasks 2.1, 2.2 complete; commits 34e9e6b (2.1), a4e26a4 (2.2). Both task reviews: spec pass, quality approved. 2.2 was BLOCKED once on the golden-count pin outside its Files set; the controller bumped it (Rule 3).
- 2026-09-10 — tasks 1.1, 1.2, 1.3, 1.4 complete; commits b826228 + 4788a89 (1.1 incl. review fix), f10d7fd (1.2), efde4ca (1.3), 7bcb712 (1.4). All four task reviews: spec pass, quality approved; 1.1 needed one fix round (task_queries coercion, Important).
- 2026-09-10 — plan written from `research-brief.md` + `design.md` (defaults D1–D3); status proposed.
- 2026-09-10 — plan review round 1 (4 blocking): subgraph drops `task` (fixed via `tasks=[task]`), REVISE note is a stored `SystemMessage` (assertions narrowed to `TASK_NOTE_PREAMBLE`), SC-9 narrowed past 7 pre-existing ruff errors, every check rewritten root-relative for `verify_summary --lane`.
- 2026-09-10 — plan review round 1 non-blocking folded in: length-equality alignment rule, `ALL_RUBRIC_NAMES` + `test_datasets.py` guard, example placement, `PYTHONPATH=.` for the dry run.
- 2026-09-10 — feasibility probe: a compiled `TravelAgentState` subgraph drops the undeclared `task` input key; fan-out now hands the slice over via `tasks=[task]` in `synthesis_worker` (Task 2.1) and `task_note` reads `tasks[0]` only.
