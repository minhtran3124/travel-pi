# gh-156 — research brief

Depth: **Standard** (intake lane `normal`; not upgraded — no Deep signal surfaced).
Source Pack: `- none (local-only; no external surface)` — the change is prompt text, a tool
docstring, and tests; no dependency, provider, or version-specific API is touched.

## What exists

- Planner prompt `apps/api/app/prompts/planner/v12.md` (active via `active.yaml`): trip creation is
  step 1 of every planner turn without an active trip (Responsibilities bullet, "How to Work" step 1,
  "No active trip yet" section). Nothing exempts a bare search.
- Supervisor v11 routes every flight search to the planner ("owns `search_flights`").
- `create_trip` (`apps/api/app/tools/trip_tools.py:324`) docstring: "Call this when there is no
  active trip, before shortlisting places or adding itinerary items." — the model reads this.
- `trip_guard` (`app/agents/subagents/_base.py`) only blocks tools that inject `trip_id`;
  `search_flights` is not one, so code never stops a trip-less search.
- Pin test `tests/prompts/test_planner_prompt.py` asserts the sentence "create the trip first, then
  add itinerary items in your next step" survives any bump.
- Eval golden `flight_search-multi_turn-vi-01` (`eval/datasets/flight_search.json`): baseline run 3
  trace `create_trip, get_trip_summary, resolve_date, search_flights` — passes only because the search
  still happened after the detour; run 2 ended before it.
- Prompt-bump convention (CHANGELOG, sibling specs gh-155/gh-146): copy vN → vN+1, edit named lines,
  point `active.yaml`, prepend a CHANGELOG entry; graph rebuild needed for a live check.

## Lightest path

Planner **v13** scoping "No active trip yet" to itinerary-writing requests plus an explicit
"search first, save later" rule; matching `create_trip` docstring; content-pin tests. No graph or
tool-registry change.

## Alternatives (why not)

- Remove `create_trip` from the planner toolset until an itinerary write is requested — needs intent
  detection the supervisor does not emit; blocks legitimate "plan my trip" turns.
- Route bare searches to concierge — contradicts supervisor v11 / #155 routing.

## Uncertainty

- LLM compliance is probabilistic; the only truth-tier proof is a keyed, Docker-backed eval run
  (`python -m eval --suite full --capability flight_search --language vi --repeat 3`), which is paid
  and outside a task Verify (>60s). Run at phase end if the environment allows; otherwise record under
  "Not auto-verified".
