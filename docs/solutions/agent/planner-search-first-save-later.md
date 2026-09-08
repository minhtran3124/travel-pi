---
problem_type: decision
module: agent/planner
tags: langgraph, prompts, planner, create_trip, search_flights, tool-ordering, intent-scoping, eval, gh-156
severity: critical
applicable_when: Writing or reviewing any agent prompt, tool docstring, or routing rule that tells a specialist to "set up" state (create a trip, open a record, pick a default) before acting — or adding a new search/lookup tool to the planner. Also when an eval trace shows a write tool (create_trip, add_itinerary_item) firing on a turn the traveller phrased as a search.
affects:
  - apps/api/app/prompts/planner/v13.md
  - apps/api/app/prompts/active.yaml
  - apps/api/app/tools/trip_tools.py
  - apps/api/tests/prompts/test_planner_prompt.py
  - apps/api/tests/tools/test_trip_tools.py
  - apps/api/eval/datasets/flight_search.json
supersedes: null
confidence: high
confirmed_at: 2026-09-08
---

## Applicable When

Any time an agent prompt, tool description, or supervisor rule makes a **write / setup step a
precondition of a turn** ("if there is no active trip, open one first"). The failure shape is
generic: the setup step gets applied to every request the specialist receives, including the
read-only ones, and burns the turn's tool rounds before the thing the traveller asked for runs.
Concretely: planner prompt bumps, new planner tools, `create_trip` wording, supervisor routing of
searches, and eval triage of `tools_expected` failures where a write tool appears before a search.

## Context

GitHub #156 (review-b7 eval, golden `flight_search-multi_turn-vi-01`): "Tôi muốn bay từ Hà Nội
đi Phú Quốc" → "Ngày 25 tháng 3 năm 2027 nhé, cho 2 người lớn". The planner called `create_trip`
and `resolve_date` and never `search_flights`. The committed baseline (run 3) "passed" but its
trace was still `create_trip, get_trip_summary, resolve_date, search_flights` — the search only
happened after an unrequested trip was opened. Cause: planner v12 made trip creation step one of
every turn without an active trip (Responsibilities bullet, "How to Work" step 1, "No active
trip yet" section), and the `create_trip` docstring said the same. Supervisor v11 routes every
flight search to the planner, so a bare search inherited the "plan a trip" preamble. Nothing in
code forced it: `trip_guard` only blocks tools that inject `trip_id`; `search_flights` runs
trip-less.

## Options Considered

1. **Prompt + docstring scoping (chosen):** planner v13 scopes "No active trip yet" to
   itinerary-writing intent and adds a "Search first, save later" section; `create_trip`'s
   model-visible description says the same; both pinned by content tests.
2. Code guard: strip `create_trip` from the planner toolset until an itinerary write is
   requested — deterministic, but needs an intent signal the supervisor does not emit and would
   block legitimate "plan my trip" turns. Kept as the fallback if v13 does not hold at k=3.
3. Route bare searches to concierge — contradicts supervisor v11 ("planner owns
   `search_flights`") and the #155 routing work.

## Decision & Rationale

**Search first, save later.** A request to find / compare / price flights, hotels, places, or
weather is a *search*, not a trip. Search tools never need an active trip, so the specialist
runs them straight away and answers with grounded options. `create_trip` is called **only** when
the traveller wants to build or save an itinerary ("add it to my trip", "save this", "plan the
rest"), and never before a search or for a trip the traveller did not ask for. The rule lives in
three places that the model actually reads — the planner prompt, the tool description, and the
pin tests — because prompt text and tool docstrings are read by the model independently and a
fix in only one leaves the other arguing for the old behaviour.

General principle for future prompts/tools: **a setup/write step must be gated on the intent
that needs it, never on the absence of state.** "No active trip → create one" is wrong; "wants
to write an itinerary and no active trip → create one" is right. State absence is not intent.

## Consequences

- Planner v13 is the active prompt; the `create the trip first, then add itinerary items in
  your next step` sentence (pinned since v11) is unchanged — it still governs itinerary writes.
- Truth-tier proof is only the keyed, Docker-backed eval
  (`python -m eval --suite full --capability flight_search --language vi --repeat 3`); prompt
  compliance is probabilistic, so a `tools_expected` regression on this golden is the signal to
  fall back to option 2.
- Any new planner search tool (e.g. a future `search_activities`) should be listed in the
  "Search first, save later" section, or the model may treat it as a planning step again.
- Eval triage: a trace where a write tool precedes the expected search is a defect even when
  the case passes — `tools_expected` only asserts inclusion, not order or absence.

## Related

- specs/gh-156-flight-search-before-create-trip/ (SUMMARY, research-brief, PLAN)
- [[supervisor-active-yaml-is-a-pointer]] — prompt bump convention (copy vN → vN+1, point active.yaml)
- [[negative-grep-is-not-absence]] — enumerate active prompts when changing a rule stated in several places
- [[llm-parses-code-computes]] — sibling principle: keep behaviour deterministic where code can decide
