# review-b7-eval-baseline-ci — Re-validation triage

Run 1: `make eval-full` (suite full, k=3, judge gpt-4o-mini, agent context premium + authenticated, 2026-09-07). 84 cases, **57 passed**, 27 failed. Classes per PLAN.md Task 3.2: **stale-golden** (expectation contradicts current main behaviour → golden edited), **agent-defect** (golden matches the prompt's stated rule, agent misbehaves → GitHub issue, golden kept), **eval-defect** (harness wrong → fixed in eval code), **eval-gap** (harness cannot exercise the path → issue, golden kept).

Two run-1 crashes fixed before the run completed: `Settings.agent_config_cache_ttl_seconds` renamed on main (Rule 3, `eval/__main__.py`, commit 864d892); GEval `MissingTestCaseParamsError` on an empty `actual_output` (eval-defect, `judged.py` guard, commit a51b28d).

| golden_id | failing checks | class | action |
| --- | --- | --- | --- |
| booking-happy-vi-01 | reply_language (empty reply → "en") | eval-defect + eval-gap | `reply_language` now `not_applicable` on empty reply (`deterministic.py`); booking path unreachable single-shot → #153 |
| booking-happy-en-01 | tools_expected book_hotel not called | eval-gap | HITL `plan_approval` interrupt precedes every tool call → #153; golden kept |
| booking-ambiguous-vi-01 | reply_language (empty) | eval-defect + eval-gap | as above; #153 |
| booking-tool_failure-vi-01 | non_empty_reply, reply_language | eval-gap | interrupt before `book_hotel(HTL-999999)` → NotFound never exercised; #153 |
| errors-ambiguous-en-01 | non_empty_reply | eval-gap | "Book something for me" interrupts with an empty draft instead of clarifying; #153 |
| errors-tool_failure-vi-01 | non_empty_reply, reply_language | eval-gap | same scenario as booking-tool_failure-vi-01; #153 |
| budget-ambiguous-en-02 | flow_match (concierge vs synthesize), reply_language (en→vi) | agent-defect | synthesize replies in Vietnamese to an English turn → #146; fan-out itself is defensible under v10 |
| budget-ambiguous-en-03 | flow_match (concierge vs budget), format_quality 0.53 | agent-defect | general budgeting advice is travel knowledge, not the trip's budget → #151 |
| dates-ambiguous-vi-01 | flow_match (concierge vs planner) | stale-golden | v10: flight search → planner; expected_flow → planner |
| dates-multi_turn-vi-01 | flow_match (concierge vs booking), reply_language (empty) | stale-golden | "đặt khách sạn" is a book intent → booking; language now n/a on empty |
| dates-multi_turn-en-01 | flow_match (concierge vs booking) | stale-golden | "I want to book a flight" → booking |
| errors-multi_turn-en-01 | flow_match (concierge vs planner) | stale-golden | v10: flight search → planner |
| flight_search-ambiguous-en-01 | search_vs_booking 0.47 | agent-defect (judged) | #154 |
| flight_search-multi_turn-vi-01 | oracle_fact_check (agent: date has passed) | stale-golden | 2026-08-25 → 2027-03-25 in turn + oracle params |
| flight_search-multi_turn-en-01 | oracle_fact_check (date has passed) | stale-golden | 2026-09-05 → 2027-03-05 |
| hotels-happy-en-02 | tools_expected (browse vs search_hotels) | stale-golden | 2026-08-10/12 had passed → 2027-03-10/12 (re-check on run 2) |
| hotels-multi_turn-vi-01 | tools_expected, oracle_fact_check | stale-golden | 2026-09-01/05 had passed → 2027-03-01/05 |
| hotels-multi_turn-en-01 | tools_expected, oracle_fact_check | agent-defect | dates were in the future; agent used `browse_hotels` and denied availability checks → #147 |
| journal-multi_turn-vi-01 | flow_match (planner vs journal) | agent-defect | itinerary edit routed to journal → #150 |
| journal-multi_turn-en-01 | format_quality 0.40 | agent-defect (judged) | #154 |
| language-ambiguous-en-01 | reply_language, response_language 0.23 | agent-defect | explicit language switch ignored → #148 |
| language-multi_turn-vi-01 | reply_language, response_language 0.20 | agent-defect | #148 |
| memory-multi_turn-vi-04 | memory_recall 0.48 | agent-defect (judged) | stated budget not reflected → #152 |
| memory-multi_turn-vi-06 | flow_match (journal vs concierge) | stale-golden | last turn is a restaurant ask → concierge; recall graded by memory_recall |
| routing-ambiguous-en-02 | flow_match (journal vs planner) | stale-golden | v10 "when in doubt → planner" |
| routing-multi-en-01 | flow_match (planner vs synthesize) | agent-defect | supervisor fans out despite v10 single-specialist rule → #149 |
| suggestions-happy-en-02 | suggestion_relevance 0.67 | agent-defect (judged, borderline) | #154 |

Golden edits: 6 flow re-derivations + 4 date moves (10 goldens). Eval code edits in this task: `evalkit/metrics/judged.py` (empty-reply guard, planned contingency) and `evalkit/metrics/deterministic.py` (`reply_language` empty-reply guard — same defect class, one file beyond the task's Files line; recorded as a Rule-1 deviation in SUMMARY).

Run 2: see SUMMARY `### Verify` (re-run after the edits above; loop capped at two runs by the plan).
