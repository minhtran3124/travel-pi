# gh-148-trip-brief-routing-fixes — Summary

Lane: normal
Confidence: medium
Reason: no manifest hard gate (prompt + agent-state wiring, no schema/route/auth change); flags existing-behavior, multi-domain, weak-proof → 3 flags = normal.
Flags: existing-behavior, multi-domain, weak-proof
Affects: app/agents/supervisor.py (routing + slot extraction), app/agents/state.py (trip_facts / reply-language injection), prompts supervisor + planner (versioned registry)
Input-type: change request
Route: using-git-worktrees → subagent-driven-development
Escalate: no (notify-and-proceed; medium confidence on a normal lane with a documented default — see Rationale)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

Assistant (turn 1 recommendation): "thêm một state kiểu **"trip brief"** (điểm đến, ngày đi, số người, budget, ngôn ngữ ưu tiên). Supervisor cập nhật nó mỗi lượt và inject vào mọi subagent … Một thay đổi này có thể xử lý cả #152, #150 và #148."

User: "ok, làm trước với trip brief + sủa #148-#152"

## What changed

No new state: the "trip brief" already existed as `trip_facts` (MIN-65 D1), and intake verified it carries destination and budget across turns. The five eval defects were instruction gaps, fixed in four places. **supervisor v13**: an explicit request to reply in a language switches it immediately and stays sticky (#148); adding an item to a day is a planner edit, not journal (#150); general cost knowledge goes to concierge, the trip's own money to budget (#151); flights + weather stays one planner job (#149). The `SupervisorIntent.language` description and the established-language hint in `make_supervisor` say the same. **communication_style v9** + `with_reply_language`: the explicit-request exception reaches every language absolute, including the blocked-on-traveller line (#148). **planner v16**: a known budget is a firm target with one approximate spend estimate, stated in Guardrails too (#152). **Shared date note** (`ground_current_date`): gh-191's "no date → must ask" now applies only before a date-bound tool call, so an undated "3-day itinerary" is answered as Day 1/2/3 — the real root cause of #152 found by the live eval (E001); never-invent-a-date stays unconditional. Live eval on the final code passes #148–#152 in scope and all three gh-191 guards (one documented detector exemption, #212); details in `### Not auto-verified`.

### Rationale

Intake found the "trip brief" already exists as `TravelAgentState.trip_facts` (MIN-65 D1): the supervisor extracts `ExtractedSlots` every turn, `merge_trip_facts` accumulates them, and `system_with_summary` injects them into every sub-agent. Ambiguity named: (A) build a new brief state vs (B) strengthen the existing `trip_facts` and fix the per-issue root causes. Picked **B** — A would duplicate a working channel. Root causes found at intake: #148 the language rule (prompt rule 4 + `SupervisorIntent.language` description + `with_reply_language` "language of their typed messages") has no carve-out for an explicit switch request; #150/#151 missing routing examples (add-item-to-day → planner; general budgeting advice → concierge); #152 budget reaches the planner (`_normalize_budget_slot("khoảng 20 triệu")` → `20 triệu`, eval replays one thread_id) but the planner is not told to size the plan to it; #149 baseline (2026-09-07) predates supervisor v12 (2026-09-09, tools-decided fan-out) — re-measure before changing.

### Alternatives considered

- New `trip_brief` state channel maintained by a dedicated node — rejected: duplicates `trip_facts`, adds an LLM call per turn, and the plumbing is already proven working.
- Live-eval scope: one `--capability` run per affected dataset (47 full-suite goldens) or a new `--id` flag in `evalkit/cli.py` — rejected: ~7× the approved spend, and the flag is eval-harness scope creep. Chosen: `run_eval_subset.py` subclasses `JsonDatasetStore` to keep the 7 goldens and delegates to `eval.__main__.main()` unchanged (dry-run selects exactly 7). `--repeat 3` repeats judged metrics only (`evalkit/runner.py:106,165`), so the agent runs once per golden.

### Deviations

- Rule 1 — Task 3.2 review m12: restored "Never invent a date the traveller did not give." as an unconditional sentence in the `ground_current_date` note (it had been folded into the date-bound-tool clause); tightened the two new tests (m13, m14). `apps/api/app/agents/state.py`, `apps/api/tests/agents/test_state.py`. Applied by the controller (one-line prompt fix + test asserts), covered by the final correctness-review.

### Review ledger (Minor findings, forwarded to final review)

- Task 1.1 (spec pass / quality approved, f662d990): (m1) v13 test does not assert the "switch to English" phrasing nor the positive `language en` few-shot line; (m2) wording drift between `SupervisorIntent.language` description and v13 rule 4 (same meaning); (m3) the ❌ quoted-phrase example is uninformative when the established language is already `en`; (m4) real-model routing unproven until Task 3.1.
- Task 1.3 round 1 (needs_fixes → fixed): Guardrails lacked the ≈-estimate exception (Important, fixed); "hard constraint" vs allowed overrun (Minor, fixed). Reviewer's "budget key may not exist" finding rejected with evidence: `_normalize_slots` writes `budget` (app/agents/supervisor.py) and `system_with_summary` renders `- budget: <value>` (app/agents/state.py).
- Task 1.3 re-review (spec pass / quality approved, 899896be + aea5445b): (m5) verify-1.3.txt labels the run "working tree over 899896be" not aea5445b (content identical to the fix diff); (m6) SC-5 is string-level only — real-model budget sizing is covered by golden memory-multi_turn-vi-04 in Task 3.1; (m7) overrun wording less direct than the draft — revisit only if eval shows silent overruns.
- Task 1.2 re-review (spec pass / quality approved, 2a423352 + b2ae0516): (m8) the ❌ quoted-phrase example states wrong and right behaviour on one line — leave v9 as shipped; (m9) SC-3 is wording-only — the request → state["language"] → directive path is proven only by Task 3.1 (language-* goldens).
- Task 2.1 (spec pass / quality approved, c2c8c115): (m10) CHANGELOG line forward-references the live-eval report — must be satisfied by Task 3.1's `eval-report.json`; (m11) verify evidence should name the HEAD sha — done from here on.
- Side effect (not a finding, recorded for audit): the one-off `api-api` container's entrypoint runs `alembic upgrade head`; the Task 3.1 dry-run upgraded the shared dev DB `api-db-1` from b8e4c1f7a305 to d4f7a2c9e1b3 (feedback_events + messages.agent_run_id, from main commit 450acd3a, already on github/main). Additive; reversible with `alembic downgrade b8e4c1f7a305` (drops feedback_events) — left to the owner.
- Task 3.2 (spec pass / quality approved, a21138ce): (m12) "never invent a date" had moved inside the date-bound-tool clause, narrowing gh-191's guarantee — controller restored it as its own unconditional sentence before the final eval (see Deviations); (m13) the allowance test matched phrases anywhere in the note — tightened to the allowance sentence; (m14) the must-ask trigger check accepted bare "trip" — tightened to "trip with dates"; (m15) SC-8 is string-level — real-model proof is Task 3.3 (memory-multi_turn-vi-04 + the three gh-191 goldens).
- Task 1.2 round 1 (needs_fixes → fixed): v9 lines 29/40 absolutes contradicted the explicit-request rule (Important, fixed); "Blocked on the Traveller" wording and a byte-stable test that only checked substring (Minor, fixed).

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit — supervisor v13 prompt + schema | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q` | 0 | 14 passed (verify-1.1.txt run at f662d990) | SC-1 |
| unit — explicit-switch selector | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q -k explicit_switch` | 0 | 4 passed | SC-2 |
| unit — with_reply_language | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state_language.py -q` | 0 | part of 33 passed (verify-1.2.txt) | SC-3 |
| unit — communication_style v9 | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_communication_style_language.py -q` | 0 | part of 33 passed (verify-1.2.txt) | SC-4 |
| unit — planner v16 budget | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_planner_prompt.py -q` | 0 | 5 passed (verify-1.3.txt) | SC-5 |
| unit — active versions + registry | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts tests/api/prompts -q` | 0 | covered by 539 passed (verify-2.1.txt, tests/prompts tests/api/prompts tests/agents) | SC-6 |
| unit — narrowed no-date rule (+ m12 fix) | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state.py -q -k ground_current_date` | 0 | 6 passed (verify-3.2.txt); task Verify 29 passed and tests/agents+tests/prompts 517 passed after the m12-m14 fix | SC-8 |
| live eval — in-scope goldens on final code | `.venv/bin/python specs/gh-148-trip-brief-routing-fixes/check_eval.py specs/gh-148-trip-brief-routing-fixes/eval-report-final.json` | 0 | report from 6cbb355a; budget-ambiguous-en-03 reply_language EXEMPT (E003, #212) | SC-7 |
| live eval — final gate incl. gh-191 + #148 tally | `.venv/bin/python specs/gh-148-trip-brief-routing-fixes/check_eval.py specs/gh-148-trip-brief-routing-fixes/eval-report-final.json specs/gh-148-trip-brief-routing-fixes/language-tally.json` | 0 | 8 PASS + 1 EXEMPT; language-ambiguous-en-01 5/5; negative check (en-03 also failing flow_match) exits 1 | SC-9 |

Whole BE suite (cited, not a Verify row per `rules/plan-format.md`): `cd apps/api && ../../.venv/bin/python -m pytest -q` → 2630 passed, 6 skipped, exit 0 at 6cbb355a (baseline before the branch: 2610 passed).

### Not auto-verified

- Live eval (Task 3.1, `eval-report.json`, code at c2c8c115, `--repeat 3` judge): 4/6 in-scope goldens pass — language-multi_turn-vi-01 (#148), routing-multi-en-01 (#149), journal-multi_turn-vi-01 (#150), budget-ambiguous-en-03 (#151). FAIL: language-ambiguous-en-01 (#148; reply_language vi, response_language 0.336) and memory-multi_turn-vi-04 (#152; memory_recall 0.411). Watch item budget-ambiguous-en-02 (#146, out of scope) fails flow_match (fan-out to synthesize), as in the baseline. `check_eval.py` exits 1.
- Diagnostic re-run of the two failures (`diag_gh148.py`, output `diag-rerun.txt`, one agent run each, no judge):
  - language-ambiguous-en-01 replied in English with `state.language=en` — 1 pass / 1 fail across two runs: the fix works but is not stable; n=2 cannot give a rate (baseline also flipped this golden between runs).
  - memory-multi_turn-vi-04: `trip_facts={'destination': 'Phú Quốc', 'budget': '20 triệu'}` — the budget reaches the planner, but the planner produced NO itinerary: it asked for a travel date. Root cause is outside the plan: the shared `ground_current_date` note ("If the traveller mentioned NO date at all, you MUST ask which date they want", app/agents/state.py) forces a date question even for an undated day-by-day suggestion, so v16's budget section never runs. Plan gap — escalated to the owner.
- Final live eval (Task 3.3, `eval-report-final.json`, code at 6cbb355a, `--repeat 3` judge): PASS language-multi_turn-vi-01, routing-multi-en-01, journal-multi_turn-vi-01, memory-multi_turn-vi-04 (#152 now passes), and all three gh-191 guards (dates-ambiguous-en-02, -vi-02, -en-03). language-ambiguous-en-01 passed its judged run and 5/5 extra single runs (`language-tally.json`, reply and state.language both en). budget-ambiguous-en-03 fails only `reply_language`: `diag-budget-rerun.txt` shows an English reply with state.language=en, and `_detect_language` returns `vi` for any Latin diacritic ("Great cafés…" → vi). Exempted by owner decision E003, tracked in #212. Watch item budget-ambiguous-en-02 (#146, out of scope) fails the same detector check this run; its fan-out to synthesize also recurs in one of three runs.
- Eval is a small sample: one agent run per golden (judge k=3), plus 5 runs for the flaky #148 case. The rates are not measured, and passing here does not prove zero regressions outside the ten goldens. `make eval-check` against `eval/baselines/main.json` was not run (paid; owner's call).
- The dev DB (`api-db-1`) was upgraded to d4f7a2c9e1b3 by the eval container's entrypoint (see Review ledger). This comes from main's migration, not from this branch.

### Rollback

- `git revert <sha>` (prompt versions are additive; `active.yaml` pointer revert restores prior behaviour)

### Harness-Delta

- none
