---
name: stays
description: Operating procedure for researching accommodation and writing /research/stays.md. Activate when tasked with the stays/hotels dimension of a dossier — it explains how to use search_hotels, browse_hotels, search_places, and nearby_places to build a hotel shortlist, what each entry must record (hotel id, area, price, why it fits), what to do when nothing is available, and the rule never to invent a hotel id or price. Read it before searching hotels or writing the stays file.
---

# Skill: stays

Research where the traveller sleeps and write `/research/stays.md`. Follow
`dossier-format` for the file path, headings, and the citation rule.

## Tools

- `search_hotels` — hotel availability and price by area/date; the source of hotel ids.
- `browse_hotels` — broader catalogue lookup when a specific search returns little.
- `search_places` — locate the neighbourhoods or landmarks the traveller wants to be
  near, so the hotel search area is right.
- `nearby_places` — check what sits around a candidate hotel (walkability, points of
  interest).

## Procedure

1. Establish the area(s) the stay should serve — near the itinerary's centre of
   gravity, a named neighbourhood, or a landmark. Use `search_places` / `nearby_places`
   to pin the area when the ask is vague.
2. Call `search_hotels` for those areas and the trip dates. Fall back to
   `browse_hotels` if availability is thin.
3. Keep a shortlist (2–5 hotels). For each, record the **hotel id**, name, area, nightly
   price, and one line on why it fits (location, price, amenities), each figure cited.
4. Note the recommended hotel id(s) to carry into the proposal.

## What belongs in `/research/stays.md`

- `# Stays` H1.
- The area(s) and dates searched.
- A shortlist, each entry with its **hotel id** and price, each cited to its tool.
- A short recommendation naming the hotel ids for the proposal.

## When a tool returns nothing

If no hotels are available, write the file with the area/dates searched and "No
availability returned (search_hotels)." Try `browse_hotels` once before concluding.
Never present a hotel that no tool returned.

## Never invent

Never write a hotel id, price, or availability that a tool did not return. A hotel id in
`/plan/proposal.json` must come from `search_hotels` or `browse_hotels`, or
`validate_proposal` rejects it.
