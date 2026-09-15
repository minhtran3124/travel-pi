---
slug: gh-148-trip-brief-routing-fixes
status: active
owner: minhtran3124
created: 2026-09-15
---

# Trip brief + routing/language fixes (#148–#152)

## 1. Motivation

The "trip brief" already exists as `TravelAgentState.trip_facts` (MIN-65 D1: supervisor
`ExtractedSlots` → `merge_trip_facts` → `system_with_summary` into every sub-agent); intake
verified the plumbing works (budget "khoảng 20 triệu" normalizes to `20 triệu`; eval replays one
thread_id). The five eval defects are prompt/instruction gaps on top of it:

- **#148** explicit "reply in English" is ignored — supervisor rule 4, `SupervisorIntent.language`
  description, `with_reply_language` and communication_style v8 all key the language off the
  language the traveller *writes in*, with no carve-out for an explicit request.
- **#150** "Thêm buổi tối ăn lẩu vào ngày 2" → journal: no example that adding an item to a day is a
  planner itinerary edit; journal's "marking itinerary items done" attracts it.
- **#151** "typical daily budget for backpacking in Vietnam" → budget: nothing says general cost
  knowledge (no trip) is concierge.
- **#152** planner receives the budget in Known trip facts but is never told to size the plan to it.
- **#149** baseline (2026-09-07) predates supervisor v12 (2026-09-09), which fixed exactly this;
  v13 adds the literal contrastive example and the live eval re-measures it.

## 2. Non-goals

- No new state channel, no change to `trip_facts` keys/reducer, no DB/schema change.
- No baseline regeneration; no golden edits; #146/#154 not in scope.
- No change to `SupervisorIntent` fields or types — descriptions only.

## Global Constraints

- New prompt versions are full copies of the currently active version plus targeted edits; never
  edit an existing `vN.md`. Active today: supervisor 12, planner 15, communication_style 8.
- Wave-1 tests read the new version explicitly (`registry.get(name, version=N)`); `active.yaml`
  is bumped only in wave 2. Existing tests that read the ACTIVE version therefore re-check v13/v16
  only in wave 2 (Task 2.1 Verify). Exception: the `SupervisorIntent.language` description, the
  established-language hint in `make_supervisor` and the `with_reply_language` wording are code,
  not versioned prompts — they go live in wave 1 and roll back only with their commit.
- Prompt rule and the matching `Field(description=...)` must say the same thing — the model reads
  both independently (#156 lesson).
- Explicit-switch rule: an explicit request to reply in a language wins immediately, whatever
  language the request itself is written in, and stays sticky afterwards; loanword/interjection
  noise still never switches. A question ABOUT a language ("How do you say 'thank you' in
  English?") is not a switch request — pinned by a negative test and a ❌ example.
- Do not re-add literal version pins: `tests/prompts/test_active_versions_load.py:18-28` removed
  them deliberately; `tests/api/prompts/test_prompt_registry_helpers.py` covers resolution.
- Eval reports under `apps/api/eval/reports/` are gitignored (`.gitignore:65`); the gh-148 report
  is written to the spec dir instead.
- Keep existing routing contracts intact: "Set a simple budget for my trip" → budget, "Log that I
  paid 50 USD" → budget, "Move day 2 before day 3" → planner, fan-out rules of v12 unchanged.
- Tests run on FakeLLM / registry only — no network, no `.env` in the worktree.
- Worktree is `../travel-pi-gh-148-trip-brief-routing-fixes`; write files via Bash (the
  branch-isolation guard refuses Edit/Write there). Never stage `.claude/settings.json`.
- Subagents implement only; the controller stages and commits (separate commands, no Claude
  attribution trailers).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
| --- | --- | --- | --- |
| SC-1 | Supervisor v13 carries the explicit-switch language rule and the #149/#150/#151 routing examples, v12 contracts kept | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q` | exit 0 |
| SC-2 | `SupervisorIntent.language` description and the established-language hint honour an explicit switch request | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q -k explicit_switch` | exit 0 |
| SC-3 | `with_reply_language` directive allows the explicitly requested language | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state_language.py -q` | exit 0 |
| SC-4 | communication_style v9 lets an explicit request switch the reply language | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_communication_style_language.py -q` | exit 0 |
| SC-5 | Planner v16 sizes the plan to a known budget and reports spend against it | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_planner_prompt.py -q` | exit 0 |
| SC-6 | With `active.yaml` at supervisor 13, planner 16, communication_style 9, every prompt/registry test passes on the active versions | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts tests/api/prompts -q` | exit 0 |
| SC-7 | On the real model the seven affected goldens pass (live eval report on this branch) | `.venv/bin/python specs/gh-148-trip-brief-routing-fixes/check_eval.py specs/gh-148-trip-brief-routing-fixes/eval-report.json` | exit 0 |

## 4. Tasks

### Task 1.1 — Supervisor v13 + schema descriptions (wave 1)

- **Files:** apps/api/app/prompts/supervisor/v13.md, apps/api/app/agents/supervisor.py, apps/api/tests/prompts/test_supervisor_prompt.py
- **Action:** Test-first: add tests (against `version=13` and `SupervisorIntent`) for each
  behaviour below, then copy v12 → v13 and edit. (a) Rule 4: an explicit request to reply in a
  language ("switch to English", "Trả lời bằng tiếng Anh được không?") sets that language
  immediately even if the request is written in another language; sticky afterwards. (b) Mirror
  (a) in the `SupervisorIntent.language` description and in the "Established conversation
  language … keep it unless the traveller clearly switches" hint in `make_supervisor` (add "or
  explicitly asks for another language"). (c) Specialist list + examples: journal records notes /
  marks items done and never adds or moves itinerary items; example "Thêm buổi tối ăn lẩu vào ngày
  2 nhé" → planner. (d) budget is THIS trip's expenses/balances/caps; general cost knowledge with
  no trip ("Break down a typical daily budget for backpacking in Vietnam") → concierge, as a
  contrastive pair with "Set a simple budget for my trip" → budget. (e) Example "Find flights to
  Tokyo and tell me the weather there" → planner, `plan=[]`. (f) Negative: a question about a
  language ("How do you say 'thank you' in English?") keeps the established language — in the
  rule text and a test. Name the (a)/(b)/(f) tests `test_*explicit_switch*` so SC-2 selects them.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py tests/agents/test_supervisor.py tests/agents/test_supervisor_language.py tests/agents/test_supervisor_slots.py tests/agents/test_supervisor_plan_semantics.py tests/agents/test_supervisor_task_queries.py -q`
- **Done:** new `version=13` tests and the listed supervisor test files pass; the pre-existing
  active-version prompt tests are re-checked on v13 in Task 2.1.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes the existing supervisor v12 prompt and the SupervisorIntent schema in supervisor.py. Produces `apps/api/app/prompts/supervisor/v13.md` and updated descriptions in `apps/api/app/agents/supervisor.py`.

### Task 1.2 — Reply-side explicit language switch (wave 1)

- **Files:** apps/api/app/prompts/communication_style/v9.md, apps/api/app/agents/state.py, apps/api/tests/agents/test_state_language.py, apps/api/tests/prompts/test_communication_style_language.py
- **Action:** Test-first. Copy communication_style v8 → v9; in "## Language" add that an explicit
  traveller request to reply in a given language overrides the typed-language rule and stays in
  effect; add a ✅ example for "Can you switch to English? Tôi muốn hỏi về khách sạn" → English.
  Add a ❌ example: "How do you say 'thank you' in English?" in a Vietnamese chat → still
  Vietnamese. Reword `with_reply_language` so the directive reads as the traveller's chosen
  language — the language they write in, or the one they explicitly asked for — keeping the
  no-op behaviour and the exact prefix `"Reply in the traveller's own language: "` + code,
  which `tests/agents/test_state_language.py:29`, `tests/agents/test_state.py:263,315,336` and
  `tests/agents/test_synthesize_node.py:30,58` assert — reword only the text AFTER the code.
  v9 keeps the "Tin" identity text (`tests/prompts/test_tin_identity.py:7`).
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state_language.py tests/agents/test_state.py tests/agents/test_synthesize_node.py tests/prompts/test_communication_style_language.py -q`
- **Done:** both test files pass; `with_reply_language` still returns `base` unchanged without a language.
- **Criteria:** SC-3, SC-4
- **Interfaces:** Consumes the existing language value in graph state. Produces `apps/api/app/prompts/communication_style/v9.md` and `with_reply_language` in `apps/api/app/agents/state.py`.

### Task 1.3 — Planner v16 honours a known budget (wave 1)

- **Files:** apps/api/app/prompts/planner/v16.md, apps/api/tests/prompts/test_planner_prompt.py
- **Action:** Test-first (against `version=16`). Copy v15 → v16 and add a section: when Known trip
  facts lists a `budget`, size hotel/food/activity choices to it, state the estimated total (or
  per-day) spend against that budget in the reply, and never ask for the budget again; when there
  is no budget, behave as v15.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_planner_prompt.py -q`
- **Done:** new `version=16` budget test passes; the pre-existing active-version planner tests
  are re-checked on v16 in Task 2.1.
- **Criteria:** SC-5
- **Interfaces:** Consumes planner v15 text and the Known trip facts block. Produces `apps/api/app/prompts/planner/v16.md`.

### Task 2.1 — Activate versions + changelog (wave 2)

- **Files:** apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md
- **Action:** Point supervisor → 13, planner → 16, communication_style → 9 (no literal version
  pin test — see Global Constraints); add one CHANGELOG entry citing #148–#152 and each edit.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts tests/api/prompts tests/agents -q -x`
- **Done:** prompt, registry and agent tests pass with the new active versions.
- **Criteria:** SC-6
- **Interfaces:** Consumes the three new prompt files. Produces `apps/api/app/prompts/active.yaml`.

### Task 3.1 — Live eval on the branch (wave 3)

- **Files:** specs/gh-148-trip-brief-routing-fixes/run_eval_subset.py, specs/gh-148-trip-brief-routing-fixes/check_eval.py, specs/gh-148-trip-brief-routing-fixes/eval-report.json
- **Action:** User approved the spend (2026-09-15). evalkit's CLI has no id filter
  (`evalkit/cli.py:30-40`), so `run_eval_subset.py` subclasses `JsonDatasetStore` to keep only the
  seven goldens (six in scope + budget-ambiguous-en-02 as a watch item) and delegates to
  `eval.__main__.main()` unchanged — dry-run selects exactly 7. `--repeat 3` repeats judged metrics
  only, so the agent runs once per golden. Run it with `--suite full --repeat 3 --out
  /spec/eval-report.json` in a one-off `api-api` container on network `api_default` with main's
  `.env` by `--env-file`, mounting THIS worktree's `apps/api` at `/app` and the spec dir at `/spec`
  (never `docker exec api-api-1`, which runs main). `check_eval.py` reads `per_case[].golden_id` /
  `.passed` and exits 0 iff all six in-scope goldens are present and passed.
- **Verify:** `.venv/bin/python specs/gh-148-trip-brief-routing-fixes/check_eval.py specs/gh-148-trip-brief-routing-fixes/eval-report.json`
- **Done:** `eval-report.json` committed in the spec dir; six in-scope goldens pass; the watch
  item's result recorded in SUMMARY.
- **Criteria:** SC-7
- **Interfaces:** Consumes the activated prompts. Produces `specs/gh-148-trip-brief-routing-fixes/eval-report.json`.

## 5. Risks

- Prompt edits shift routing elsewhere — mitigated by keeping v12 contrastive tests on v13 and the
  live eval; the full eval-check gate is the owner's call.
- Explicit-switch detection could fire on a quoted phrase ("how do you say X in English?") — the
  rule names a request to *reply* in a language, and a test pins the wording.
- Changing communication_style shifts every sub-agent's cached prefix once (one-time cache miss).
- Reverting `active.yaml` alone does NOT undo the wave-1 code-level wording in `supervisor.py` /
  `state.py`; roll back with `git revert` of those commits.

## 6. Status Log

- 2026-09-15 — plan proposed (normal lane, notify-and-proceed).
- 2026-09-15 — review iteration 1: 7 issues + 2 recommendations applied.
- 2026-09-15 — review iteration 2: items 1–7 resolved; 1 new issue (with_reply_language prefix pins) applied; plan approved.
