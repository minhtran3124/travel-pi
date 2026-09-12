# specialist-task-description — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (intent-review finding 1, after the correctness-review fix)
- date: 2026-09-10
- trigger: ambiguous-direction
- question: Should single-intent turns still get a task note, now that the note lives in the system prompt?
- context: The intent says "Supervisor sinh `query` riêng cho từng task thay vì copy nguyên câu user". On a single-intent turn the supervisor has no split to make, so `task_queries` is null and the task query IS the user's sentence. That sentence is then copied into the specialist's system prompt as "Your task for this turn". design D3 chose "both paths" when the note was a trailing message; its rationale ("cache-neutral, appended after the history") stopped being true when the correctness fix folded the note into the leading system message. A per-turn query in the system prompt now changes the cached prefix on every single-intent turn — the common path — for no new information. Blocks the review receipt and the PR.
- options:
  - A) (recommended) Add the note only when the supervisor actually split the message: skip it when the task's query equals the last user message. Single-intent turns and fan-out fallbacks go back to main's exact model input (no duplication, no cache change); only fan-out turns with real `task_queries` carry a note. Small change in `with_task_note` (compare against the last HumanMessage) plus tests; SC-5 single-intent wording changes.
  - B) Keep the note on both paths as built. Every specialist turn restates the request in the system prompt; step 3 of the review (reflection sees the question) can reuse it. Accept the unmeasured cache cost on every turn.
  - C) Fan-out only: note only inside `synthesis_worker`. Same effect as A for today's inputs, but a future single-intent split (if the prompt ever emits one query for one specialist) would be ignored.
- default_if_no_response: BLOCK
- decision: A — add the note only when the supervisor actually split the message (skip when the query equals the last user message)
- decided_by: minhtran3124 (user, in session)
- decided_at: 2026-09-10

## E002

- raised_by: orchestrator (intent-review finding 3)
- date: 2026-09-10
- trigger: ambiguous-direction
- question: Does "Cần thêm golden multi-intent để đo" require running the paid judged eval before the PR, or only adding goldens that can measure?
- context: Two fan-out goldens (`routing-multi-en-05`, `routing-multi-vi-01`) and the judged `ask_coverage` rubric are added and pass their offline schema tests. Nothing has measured the effect: `make eval-check` is the repo's local, paid, manual gate (84 agent turns + ~105 judge calls at k=3, real key; no CI judge, decision E002 of review-b7). It also is the only check for a routing regression from supervisor v13. Blocks the review receipt and the PR.
- options:
  - A) (recommended) Run `make eval-check` in a one-off container on this branch (the dev container mounts main) before opening the PR; record before/after for `routing` and the two new goldens in SUMMARY; refresh the baseline only if the change is intended.
  - B) Open the PR with the eval listed under `Not auto-verified`; run it before merge instead.
  - C) Adding the goldens is the whole ask; no eval run for this change.
- default_if_no_response: BLOCK
- decision: A — run `make eval-check` on this branch in a one-off container before opening the PR; record before/after in SUMMARY
- decided_by: minhtran3124 (user, in session)
- decided_at: 2026-09-10

## E003

- raised_by: orchestrator (E002 eval results)
- date: 2026-09-10
- trigger: in-flight
- question: Given that the judged eval shows no measurable benefit and the v13 prompt regresses routing, what ships?
- context: `main` already answers both asks of the two fan-out goldens (ask_coverage 0.79 each); with task notes the scores scatter 0.54–0.92 on single samples, so no gain is shown. Supervisor v13 drops the budget+concierge fan-out on `routing-multi-en-03` in 6/18 probe samples vs 0/30 for v12 and main. Under v12 the model still emits `task_queries` from the schema description (12/12), so the plumbing works without v13. The artifact assumed "giá trị cao"; the evidence does not support that yet. Blocks the review receipt and the PR.
- options:
  - A) (recommended) Ship the plumbing without v13: set `active.yaml` supervisor back to 12, delete `supervisor/v13.md` and its CHANGELOG entry and prompt test; keep the `task_queries` field and description, the fan-out task note, E001 and the single-task guard. Removes the measured regression; the feature stays inert-to-positive. Record "value not demonstrated" in the PR, and follow up with a larger eval (several agent samples per golden, more fan-out goldens) before claiming a benefit.
  - B) Ship as built (with v13). Accept the routing regression on budget+concierge messages.
  - C) Do not ship: close the branch and keep the measurement as the finding (step 2 of the review does not pay off on current goldens).
  - D) Hold: first extend the eval (e.g. 5 agent samples per fan-out golden, 6+ fan-out goldens) on main vs branch-without-v13, then decide.
- default_if_no_response: BLOCK
- decision: A — ship without v13: supervisor back to v12, v13.md + its CHANGELOG entry + prompt test removed; keep the task_queries field, fan-out task note, E001 and the single-task guard; the PR states the value is not demonstrated
- decided_by: minhtran3124 (user, in session)
- decided_at: 2026-09-10
