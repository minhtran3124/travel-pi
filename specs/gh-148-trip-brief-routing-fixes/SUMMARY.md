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

_(pending — filled at delivery)_

### Rationale

Intake found the "trip brief" already exists as `TravelAgentState.trip_facts` (MIN-65 D1): the supervisor extracts `ExtractedSlots` every turn, `merge_trip_facts` accumulates them, and `system_with_summary` injects them into every sub-agent. Ambiguity named: (A) build a new brief state vs (B) strengthen the existing `trip_facts` and fix the per-issue root causes. Picked **B** — A would duplicate a working channel. Root causes found at intake: #148 the language rule (prompt rule 4 + `SupervisorIntent.language` description + `with_reply_language` "language of their typed messages") has no carve-out for an explicit switch request; #150/#151 missing routing examples (add-item-to-day → planner; general budgeting advice → concierge); #152 budget reaches the planner (`_normalize_budget_slot("khoảng 20 triệu")` → `20 triệu`, eval replays one thread_id) but the planner is not told to size the plan to it; #149 baseline (2026-09-07) predates supervisor v12 (2026-09-09, tools-decided fan-out) — re-measure before changing.

### Alternatives considered

- New `trip_brief` state channel maintained by a dedicated node — rejected: duplicates `trip_facts`, adds an LLM call per turn, and the plumbing is already proven working.
- Live-eval scope: one `--capability` run per affected dataset (47 full-suite goldens) or a new `--id` flag in `evalkit/cli.py` — rejected: ~7× the approved spend, and the flag is eval-harness scope creep. Chosen: `run_eval_subset.py` subclasses `JsonDatasetStore` to keep the 7 goldens and delegates to `eval.__main__.main()` unchanged (dry-run selects exactly 7). `--repeat 3` repeats judged metrics only (`evalkit/runner.py:106,165`), so the agent runs once per golden.

### Deviations

- none

### Review ledger (Minor findings, forwarded to final review)

- Task 1.1 (spec pass / quality approved, f662d990): (m1) v13 test does not assert the "switch to English" phrasing nor the positive `language en` few-shot line; (m2) wording drift between `SupervisorIntent.language` description and v13 rule 4 (same meaning); (m3) the ❌ quoted-phrase example is uninformative when the established language is already `en`; (m4) real-model routing unproven until Task 3.1.
- Task 1.3 round 1 (needs_fixes → fixed): Guardrails lacked the ≈-estimate exception (Important, fixed); "hard constraint" vs allowed overrun (Minor, fixed). Reviewer's "budget key may not exist" finding rejected with evidence: `_normalize_slots` writes `budget` (app/agents/supervisor.py) and `system_with_summary` renders `- budget: <value>` (app/agents/state.py).
- Task 1.2 round 1 (needs_fixes → fixed): v9 lines 29/40 absolutes contradicted the explicit-request rule (Important, fixed); "Blocked on the Traveller" wording and a byte-stable test that only checked substring (Minor, fixed).

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |

### Not auto-verified

- Real-model behaviour on the 7 affected goldens — needs a live eval run (paid, Docker db + .env); pending.

### Rollback

- `git revert <sha>` (prompt versions are additive; `active.yaml` pointer revert restores prior behaviour)

### Harness-Delta

- none
