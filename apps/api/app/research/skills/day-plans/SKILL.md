---
name: day-plans
description: Operating procedure for building per-day itineraries and writing /research/days/day-N.md. Activate when tasked with the day-plans dimension of a dossier — it explains how to use search_places, nearby_places, resolve_place, get_route, get_city_route, get_weather, get_climate, and get_air_quality to shape each day, the hard rule that every day has meals and at most three activities, what to do when a tool returns nothing, and the rule never to invent a place id. Read it before planning days or writing any day file.
---

# Skill: day-plans

Turn the trip into day-by-day plans, one file per day at `/research/days/day-N.md`
(numbered from 1). Follow `dossier-format` for paths, headings, and the citation rule.

## Tools

- `search_places` — find candidate attractions, restaurants, and sights; the source of
  place ids.
- `nearby_places` — cluster things that are close together so a day flows.
- `resolve_place` — turn a named place into a concrete place record with an id.
- `get_route`, `get_city_route` — check travel time between the day's stops so the day
  is realistic.
- `get_weather` — near-term forecast for dated trips.
- `get_climate` — typical conditions when the trip has no firm dates.
- `get_air_quality` — flag days where outdoor plans should shift.

## Procedure

1. Decide how many days to plan from the trip dates/duration. Create one
   `day-N.md` per day.
2. For each day, pick a compact geographic cluster: use `search_places` /
   `nearby_places`, and `resolve_place` to fix ids. Order the stops and sanity-check
   travel time with `get_route` / `get_city_route`.
3. Check conditions: `get_weather` (dated) or `get_climate` (undated), and
   `get_air_quality`. If conditions are poor, prefer indoor stops and say why.
4. **Each day must include meals and no more than three activities.** Meals (breakfast
   / lunch / dinner as fits) are named places with ids where a tool provided them.
   Keep activities to three so the day is achievable, not a checklist.

## What belongs in each `/research/days/day-N.md`

- `# Day N — <area/city>` H1.
- A short line on weather/air quality for the day, cited.
- The ordered stops with times, each activity and meal naming its **place id** and the
  tool that produced it.
- No more than three activities; meals are present.

## When a tool returns nothing

If `search_places` returns nothing for an area, write the day file with what was
searched and "No places returned (search_places)", and keep the day sparse rather than
inventing stops. A missing forecast is noted, not guessed.

## Never invent

Never write a place id, name, opening time, or distance that a tool did not return. A
place id in `/plan/proposal.json` must come from `search_places`, `nearby_places`, or
`resolve_place`, or `validate_proposal` rejects it.
