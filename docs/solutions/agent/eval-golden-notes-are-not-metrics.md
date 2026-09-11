---
problem_type: failure
module: agent/eval
tags: eval, goldens, metrics, verification, dates, ground-current-date, hollow-gate, a-b-test, tool-args
severity: critical
applicable_when: Before naming an eval golden, a capability, or a test file as the gate for a behaviour change — read which metrics it declares, not its name, capability or notes. Also when a golden's `notes` describe a behaviour ("resolves or asks rather than guessing") and you are about to trust that it checks it.
affects:
  - apps/api/eval/datasets/dates.json
  - specs/prompt-caching-system-prefix/evidence/date_rule_probe.py
supersedes: null
confidence: high
confirmed_at: 2026-09-10
---
## Applicable When

Any time an eval golden, a capability bucket, or a test is cited as the proof that a behaviour
still holds. The name and the notes of a golden describe what its author meant it to test. Only
its declared metrics say what it actually checks.

## Symptom

`prompt-caching-system-prefix` moved the date-grounding note from the start to the end of every
agent system prompt. That note carries hard rules — "if the traveller mentioned no date, you MUST
ask; never fall back to today" and "resolve relative dates with the resolve_date tool". A reviewer
judged this a real behavioural risk. The plan, the reviewer and the draft PR all named the same
gate for it: the `dates` eval goldens. They passed.

## Wrong Approach

Trusting the goldens because of their capability (`dates`), their scenario names (`ambiguous`,
`multi_turn`) and their notes. `dates-ambiguous-vi-01`'s note reads "a good answer resolves it
(resolve_date) or asks which day, rather than guessing" — exactly the rule under test.

## Why It Failed

Every date golden declares only `flow_match`, `reply_language` and `non_empty_reply`; the two smoke
ones add `tools_expected: [get_weather]`. **No metric checks a date.** A golden would pass if the
model silently searched for today. The notes state the intent and nothing enforces it.

A direct test showed what the goldens could not. Run the same probe against `main` (note first) and
the branch (note last), k=3, asking for a flight with no date given: the agent called
`search_flights` with **today's date and presented the results as if today had been requested, 6
times out of 6, on both versions** — a pre-existing production bug that every date golden passes.
The eval gate was not merely weak for this change; it was blind to a live violation of the rule it
was cited as guarding.

## Correct Approach

1. Before citing a golden as a gate, read its `metrics` list and ask: *if the behaviour broke, which
   of these would fail?* If the answer is none, it is not a gate for that behaviour.
2. Make the check mechanical where the behaviour leaves a trace. The eval runner already returns
   every tool call with its arguments (`evalkit.types.Trace.tool_calls`), so "never invent a date"
   becomes: *if the traveller gave no date, no search tool may receive one.* No judge needed.
3. A/B the two code versions with the same probe, so a failure can be attributed. Here it separated
   "this change broke it" (no — equal or better on every probe) from "it was already broken" (yes).
   The probe and both runs are in `specs/prompt-caching-system-prefix/evidence/`.

## Guardrail

proposed: an `evalkit` metric, `no_invented_date`, that fails a turn when a search tool
(`search_flights.departure_date`, `search_hotels.check_in`/`check_out`) receives a date the
traveller's turns never supplied, plus goldens for the no-date case in `eval/datasets/dates.json`
that declare it. The no-date golden would be red on `main` today, which is the point — target path
`apps/api/evalkit/metrics/` and `apps/api/eval/datasets/dates.json`.

## Related

- docs/solutions/agent/concierge-hotel-tool-choice.md — the sibling lesson: read the prompt, not a
  golden's note about the prompt.
- docs/solutions/agent/prompt-caching-implicit-idle-eviction.md
- docs/solutions/agent/planner-search-first-save-later.md — a likely cause of the no-date bug
  (search-first pushes an immediate search, and `search_flights` requires a date), not verified.
