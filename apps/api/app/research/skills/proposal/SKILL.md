---
name: proposal
description: The exact JSON schema and id rules for /plan/proposal.json, the machine-readable output of a trip-research run. Activate before writing or editing the proposal — it fixes the object shape (itinerary, shortlist, flights, hotels, budget_estimate), the field types of each itinerary entry, and the hard rule that every id must come from a tool result and never be invented. Read it whenever you assemble the proposal so it passes validate_proposal.
---

# Skill: proposal

`/plan/proposal.json` is the machine-readable proposal the traveller can apply to the
real trip. The grader runs `validate_proposal` against it, which checks every id against
the database. Get the schema and the ids exactly right.

## Exact schema

```json
{
  "itinerary": [
    {"day": 1, "time": "09:00", "place_id": "<id>", "title": "<short>", "notes": "<optional>"}
  ],
  "shortlist": ["<place_id>", "..."],
  "flights": ["<offer_id>", "..."],
  "hotels": ["<hotel_id>", "..."],
  "budget_estimate": 0
}
```

- `itinerary` — an ordered list of entries. Each entry has:
  - `day` — integer, 1-based, matching the `/research/days/day-N.md` files.
  - `time` — the stop's time as a string (e.g. `"09:00"`).
  - `place_id` — a place id from a tool result.
  - `title` — a short label for the stop.
  - `notes` — optional free text; omit or leave empty when there is nothing to add.
- `shortlist` — a list of `place_id`s worth considering that did not land in the
  itinerary.
- `flights` — a list of flight `offer_id`s from `search_flights`.
- `hotels` — a list of `hotel_id`s from `search_hotels` / `browse_hotels`.
- `budget_estimate` — a number: the trip's estimated total, built from the cited figures
  in `/research/budget.md`, `/research/flights.md`, and `/research/stays.md`.

## Id rule (load-bearing)

**Every id in the proposal must come from a tool result. Never invent one.**

`search_places`, `search_flights`, `search_hotels` and `browse_hotels` end with an
"Ids for the proposal" list — `Name → place_id <id>`, `VN1823 SGN→PQC … → offer_id <id>`,
`Hotel name → hotel_id <id>`. Copy the id after the arrow exactly. A name, a flight number
(`VN422`) or a hotel code is not an id and fails validation.

- `place_id` values come from `search_places`, `nearby_places`, or `resolve_place`.
- `offer_id` values come from `search_flights`.
- `hotel_id` values come from `search_hotels` or `browse_hotels`.

`validate_proposal` checks each id against the DB (places, flight offers, hotels). An
invented or mistyped id fails validation and forces a revision. If a dimension found
nothing, leave its list empty rather than fabricating an id.

## Building and revising

Assemble the proposal only from ids already written (with citations) in the dimension
files. On a revise turn, use `edit_file` to change only the entries that change; keep the
schema and the surviving ids intact.
