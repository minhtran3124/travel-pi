# gh-153-eval-hitl-auto-approve — Task 3.1 triage

Paid run (`make eval-full`, suite full, k=3, judge gpt-4o-mini, premium + authenticated) on branch `fix/gh-153-eval-hitl-auto-approve` after waves 1–2 (runner resumes `plan_approval` interrupts for `hitl: approve` goldens). A first attempt was aborted mid-run when the Docker dev stack (`api-db-1`, `api-api-1`) was stopped externally (`Exited (0)`); the stack was brought back with `docker compose up -d` and the run repeated from scratch — only the repeated run is used.

Result: **67/84** (previous baseline, review-b7 run 3: 58/84). Below threshold: budget 4/6, hotels 3/6, journal 2/4.

## The 12 `hitl: approve` goldens

| golden_id | before | after | note |
| --- | --- | --- | --- |
| booking-happy-en-01 | FAIL | PASS | resumed → `book_hotel` ran; `non_empty_reply` + `tools_expected` now pass |
| booking-happy-en-02 | FAIL | PASS | |
| booking-happy-vi-01 | FAIL | PASS | |
| booking-multi_turn-en-01 | PASS | PASS | turn-2 interrupt now resumed instead of abandoned |
| booking-multi_turn-vi-01 | PASS | PASS | |
| booking-tool_failure-vi-01 | FAIL | PASS | `book_hotel(HTL-999999)` NotFound surfaced gracefully — the scenario the golden was written for is finally exercised |
| dates-multi_turn-en-01 | FAIL | PASS | |
| dates-multi_turn-vi-01 | FAIL | FAIL | `flow_match` expected booking, got concierge — routing variance on "Tôi muốn đặt khách sạn ở Phú Quốc" (agent-side; #148/#150-class routing flakiness), not a resume defect; golden kept |
| errors-tool_failure-vi-01 | FAIL | PASS | |
| routing-ambiguous-en-01 | FAIL | PASS | |
| suggestions-happy-en-04 | FAIL | PASS | |
| suggestions-happy-vi-04 | FAIL | PASS | |

Stale "fails in baseline — see #153" note suffixes were removed from the 8 goldens that now pass and still carried it.

## Other flips vs the previous baseline (run-to-run variance, tracked issues stay open)

- pass → fail: `language-multi_turn-vi-01` (#148), `suggestions-happy-en-05` (judged 0.36, #154 class).
- fail → pass: `language-ambiguous-en-01` (#148), `suggestions-happy-en-02` (#154).

## Baseline

`eval/baselines/main.json` regenerated from this run (`make eval-baseline`); `make eval-compare` against it exits 0. The 17 remaining failures are agent defects already tracked (#146 #147 #148 #149 #150 #151 #152 #154 #155 #156) or judged variance; #153's harness gap is closed.
