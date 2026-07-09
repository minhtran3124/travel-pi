# SUMMARY — MIN-58 eval-harness calibration fix

Lane: normal
Confidence: medium
Reason: changes existing eval-harness behavior (#8 existing-behavior); minor open question on default scoring for cases with no `metrics` label — a reasonable backward-compatible default exists, so proceed.
Flags: existing-behavior, weak-proof
Affects: apps/api/eval/ (internal eval tooling — no API/client contract, no DB schema, no auth)
Input-type: Change request
Route: using-git-worktrees → subagent-driven-development (single cohesive task)
Escalate: no (no hard gate; direction confirmed by user)

## Intent

User request (verbatim, across turns):
- `/feature-intake` → "fix bug ở trên trước"
- On diagnosis showing the bug is in the eval (not the agent), chose: **"Fix eval A+B+C rồi re-run baseline"**

Where A/B/C are:
- **A** — make `run_deepeval` honor each case's `metrics` field so a G-Eval rubric only scores the cases that declare it (stop fanning all 4 rubrics over all 18 cases).
- **B** — fix `datasets/tools.json`: the two date-less hotel info searches expect `search_hotels` but the correct tool after the MIN-51/MIN-46 split is `browse_hotels`.
- **C** — tighten the `search_vs_booking` rubric so an empty result (no catalog match) is not conflated with "pushing booking"; handle the Hanoi-<$50 data-gap case.
- Then **re-run the baseline** and record the corrected numbers.

## Rationale

Diagnosis (read-only, this session) proved the low baseline scores are eval artifacts, not agent
regressions: on the correct denominator the agent scores 4/5 on search-intent and never pushes
booking (MIN-51 OK); the two "tool-correctness" misses are the agent correctly choosing
`browse_hotels` (date-less info search) while the dataset stale-expects `search_hotels` (the
dated availability/booking-flow tool). Fixing the eval makes the baseline trustworthy.

## Alternatives considered

- Fix only B (dataset) — smaller, but leaves the fan-out (A) inflating false negatives across
  all rubrics; user chose the full set.
- "Fix" the agent — rejected: diagnosis shows no agent regression; MIN-51/MIN-46 are correct.

Open question (A): cases with no `metrics` field. Default chosen — **honor `metrics` when
present; when absent, apply the current full set** (backward-compatible), and populate `metrics`
on the datasets so scoring is explicit. Recorded so the reviewer can challenge it.

## Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| unit tests | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/eval -q` | 0 | 27 passed, no network (+2 new tests for per-case filtering) |
| lint | `cd apps/api && ../../.venv/bin/ruff check eval tests/eval` | 0 | clean |
| keyed baseline | `LLM_MODEL=gpt-5.4-mini ... python -m eval.run_deepeval` (wrapper) | 0 | Run 3 recorded in `../min-58-chatbot-eval-deepeval/BASELINE.md` |

## Deviations

- Rule 1 — Dropped the `no_hallucination` rubric assignment I had briefly added to the fact-
  producing cases. Assigning it surfaced that the rubric only sees INPUT+ACTUAL_OUTPUT (no tool
  results) so it penalizes every concrete fact as "invented" (meaningless 2/7). Recording a
  false metric is worse than none; left `no_hallucination` defined but unassigned. See follow-up.

## Follow-ups (discovered)

- **Wire grounding context for `no_hallucination`**: capture tool-result output in
  `harness.run_case` as `LLMTestCase.retrieval_context`, add `RETRIEVAL_CONTEXT` to the rubric's
  `evaluation_params`, then re-assign it to hotel/flight cases. Only then is Fact Grounding real.
- `search_vs_booking` scoring is LLM-judge non-deterministic (3/5 ~ 4/5 across same-day runs);
  consider a larger intent dataset or a stricter/structured judge for stability.

## Rollback

- Revert code: `git revert <sha>` (eval-only change; no migration, no data, no contract).
