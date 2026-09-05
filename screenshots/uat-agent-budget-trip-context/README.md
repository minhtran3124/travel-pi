# UAT — agent-budget-trip-context (PR #142)

**Date:** 2026-09-05
**Environment:** local Docker (`api-api-1`, Postgres `api-db-1`), Next.js dev server, real Supabase auth
**Test account:** `uat-budget-test@example.com` (seeded via `scripts/seed_supabase_user.py`, id `014af01b-5cbf-480b-94df-f4ac1adcdc66`)
**Test trip:** "Da Nang UAT Trip", id `8ff441a7-6d0e-4b55-91ed-fdfa05b4158e`, Nov 10–14 2026 (4 nights), 2 travelers, no budget cap at start

## Original incident (reproduced verbatim)

> user: pls set simple budget for trip
> bot (before fix): I can do that, but I'm still missing one detail: how many days is your trip?

## Result

Sent the exact same message, `pls set simple budget for trip`, with no prior context beyond opening the trip. The bot did **not** ask for the day count. Full response:

> Done — I set a simple budget for your Da Nang trip 🌴
> Activities: $160
> Buffer: $346
> That makes your total trip budget $506 for 2 travelers over **4 nights**. Flights and hotels are still uncapped, since you didn't give me those costs.
> If you want, Tin can add those next.

"4 nights" is derived automatically from the trip's Nov 10–14 dates — never asked. Flights/hotels are left uncapped because no price was given, instead of being set to a $0 cap (the bug the correctness review caught and fixed on the sibling `agent-tool-round-budget` branch).

## Evidence

| File | Shows |
|---|---|
| `01-trip-page-no-budget-cap.png` | Trip before the test: "REMAINING: No cap" |
| `02-typed-original-incident-message.png` | The exact incident message typed into the chat |
| `03-bot-sets-budget-no-day-question.png` | Bot's reply — no clarifying question, budget set directly |
| `04-tool-activity-and-full-response.png` | Expanded tool-activity panel + full response text, including the uncapped-flights/hotels explanation |
| `05-budget-tab-flights-hotels-uncapped.png` | Budget tab: Flights `—`, Hotels `—`, Activities $160, Buffer $346, Total $506 |

**Backend log** (`docker logs api-api-1`), confirming the designed tool sequence:

```
node=supervisor
node=budget (assistant)
[tool] get_trip_summary called
[tool] get_trip_budget called
[tool] estimate_trip_budget called
node=budget (assistant)
[tool] set_trip_budget called
node=budget (assistant)
```

**Database row** (`trips.budget_caps` for the test trip), confirming persistence with no $0 caps:

```json
{"activities": 160.0, "buffer": 346.0}
```

## Verdict

PASS. The reported symptom (bot asks "how many days is your trip?") does not reproduce. The budget agent reads the trip's dates automatically, estimates a per-category budget, and persists it — leaving categories with no known price uncapped rather than capped at $0.
