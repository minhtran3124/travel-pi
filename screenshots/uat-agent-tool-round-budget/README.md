# UAT — agent-tool-round-budget (PR #143)

**Date:** 2026-09-05
**Environment:** local Docker (`api-api-1`, Postgres `api-db-1`), Next.js dev server, real Supabase auth
**Test account:** `uat-budget-test@example.com` (id `014af01b-5cbf-480b-94df-f4ac1adcdc66`, reused from the sibling UAT)
**Test trip:** "Da Nang 6-Day Itinerary UAT", id `8c5f31f4-fde8-46b0-9464-5cd2f802e6dd`, Dec 1–6 2026 (6 days), 2 travelers, empty itinerary at start

## Original incident (reproduced by shape)

The reported crash (container-log screenshot) was a `GraphRecursionError` while building a multi-day itinerary. The failing turn's backend log showed 8 completed rounds (`get_trip_summary`/`recall_past_trips`/`search_places` + 6× `add_itinerary_item`, one call per round) before dying on round 9 — `agent_recursion_limit=25` with `trip_guard` costing 3 super-steps/round capped a turn at 8 rounds.

## Test request

> Plan my whole 6-day Da Nang trip, day by day, with a specific place suggestion for each day

This deliberately reproduces the same round count as the incident: `get_trip_summary` → `recall_past_trips` → `search_places` → 6× `add_itinerary_item` (the model did not batch the writes despite planner v12's new instruction — it chose one item per round here, which is a valid model choice, not a defect), i.e. **9 sequential tool-calling rounds**, one more than the incident's crash point.

## Result

**PASS — no `GraphRecursionError`.** The turn completed:

- Backend log's own summary matches: the tool-activity panel reads **"Sorted 9 things for your trip · 22s"**.
- The full 6-day itinerary rendered in the UI, one item per day (Days 1–6), with no missing or duplicated days.
- `grep -c "GraphRecursionError"` over the container logs for this run: **0**.
- `SELECT count(*) FROM trip_items WHERE trip_id = …`: **6** (exactly one per day, no duplicates from a retry).
- The bot's own closing summary lists the correct day-by-day plan with no truncation, followed by a reflection pass (`node=reflection revisions=1` → `reflection → END (no revision)`), also completing cleanly.

Under the pre-fix topology (`trip_guard` visited every round, 3 super-steps/round), 9 rounds require `3×9+1 = 28` super-steps — over the unchanged `agent_recursion_limit=25` — and would have failed exactly like the original incident. Under the fix (`_route_after_assistant` skips the guard's step when the trip is already active), 9 rounds cost `2×9+1 = 19` super-steps, comfortably under budget.

## Evidence

| File | Shows |
|---|---|
| `01-trip-6-days-empty.png` | Trip before the test: 6 days, no itinerary items |
| `02-typed-plan-whole-trip-request.png` | The test request typed into the chat |
| `03-bot-completed-full-itinerary.png` | Chat + itinerary panel right after completion — no error, full 6-day plan on both sides |
| `04-full-6-day-itinerary-view.png` | Full-page capture of the rendered Day 1–6 itinerary |
| `05-sorted-9-things-panel-expanded.png` | Expanded tool-activity panel confirming **9** tool rounds ran in this one turn |

**Backend log**, the tool sequence for the turn (`docker logs api-api-1`):

```
node=planner (assistant) → get_trip_summary
node=planner (assistant) → recall_past_trips
node=planner (assistant) → search_places
node=planner (assistant) → add_itinerary_item (day 1)
node=planner (assistant) → add_itinerary_item (day 2)
node=planner (assistant) → add_itinerary_item (day 3)
node=planner (assistant) → add_itinerary_item (day 4)
node=planner (assistant) → add_itinerary_item (day 5)
node=planner (assistant) → add_itinerary_item (day 6)
node=reflection revisions=0 → reflection → planner (revise)
node=planner (assistant)
node=reflection revisions=1 → reflection → END (no revision)
```

No `GraphRecursionError` anywhere in the run's logs.

## Verdict

PASS. A request shaped like the one that originally crashed (same tool sequence, one round past the incident's crash point) now completes end to end, with the full itinerary persisted and rendered, and zero recursion errors.
