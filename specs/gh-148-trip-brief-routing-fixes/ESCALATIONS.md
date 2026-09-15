# gh-148-trip-brief-routing-fixes — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator
- date: 2026-09-15
- trigger: in-flight
- question: #152's live-eval failure is caused by the shared gh-191 date rule ("no date → MUST ask", `ground_current_date` in app/agents/state.py), not by the planner ignoring the budget — narrow that shared rule, carve out only in planner v16, or ship #148–#151 and leave #152 open?
- context: Task 3.1 — memory-multi_turn-vi-04 fails (planner asks for a date instead of giving the itinerary; budget is in trip_facts). A plan gap: the plan assumed #152 was a planner-prompt problem.
- options:
  - A) Narrow `ground_current_date`: ask for a date only before a date-bound tool call (flight/hotel search, booking, dated trip); an undated day-by-day suggestion proceeds as Day 1/2/3; keep gh-191's never-invent-a-date guarantee. Re-run memory-vi-04 plus the gh-191 date goldens for regressions.
  - B) Planner-v16-only carve-out — smaller blast, but the date note is appended after the prompt and may still win.
  - C) Ship #148–#151; open #152 follow-up with the new root cause.
- default_if_no_response: BLOCK
- decision: A — narrow the shared date rule, with a regression eval on the gh-191 date goldens
- decided_by: minhtran3124 (owner, via AskUserQuestion)
- decided_at: 2026-09-15

## E002

- raised_by: orchestrator
- date: 2026-09-15
- trigger: in-flight
- question: language-ambiguous-en-01 (#148) passed 1 of 2 real-model runs — accept, or measure more?
- context: Task 3.1 eval run failed it (reply in vi); the diagnostic re-run passed (reply en, state.language=en).
- options:
  - A) Measure 5 more single runs (no judge) on the final code; accept at ≥4/5, else investigate.
  - B) Accept as flaky; record 1/2 in the PR and #148.
- default_if_no_response: BLOCK
- decision: A — measure 5 more runs on the final code
- decided_by: minhtran3124 (owner, via AskUserQuestion)
- decided_at: 2026-09-15

## E003

- raised_by: orchestrator
- date: 2026-09-15
- trigger: in-flight
- question: The final eval fails only budget-ambiguous-en-03's reply_language, and the diagnostic proves the eval's detector reads any Latin diacritic ("cafés") as Vietnamese while the agent replied in English (state.language=en) — record and exempt, fix the detector here, or re-run?
- context: Task 3.3 — SC-9 gate (`check_eval.py`) exits 1 on that single check; everything else in scope and all three gh-191 goldens pass.
- options:
  - A) Record it: a documented, printed exemption for that one check in `check_eval.py`, SC-7/SC-9 wording amended, and a GitHub issue to fix the detector separately (it moves `eval/baselines/main.json`).
  - B) Fix `_detect_language` in this PR (eval-harness scope, re-baseline risk) and re-run the budget goldens.
  - C) Re-run the golden until it passes (retry, not a fix).
- default_if_no_response: BLOCK
- decision: A — record + open issue; issue #212 opened
- decided_by: minhtran3124 (owner, via AskUserQuestion)
- decided_at: 2026-09-15
