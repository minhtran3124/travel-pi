---
name: entry-and-season
description: Operating procedure for researching entry requirements and seasonal conditions, writing /research/entry-and-season.md. Activate when tasked with the entry/season dimension of a dossier — it explains how to use get_visa, get_local_tips, search_travel_knowledge, get_climate, and get_packing to cover visas and entry rules, local etiquette, typical weather, and what to pack, what to do when a tool returns nothing, and the rule never to invent an entry rule or a figure. Read it before researching entry/season or writing that file.
---

# Skill: entry-and-season

Research what the traveller needs to enter the country and what the season is like, and
write `/research/entry-and-season.md`. Follow `dossier-format` for the path, headings,
and the citation rule.

## Tools

- `get_visa` — visa and entry requirements for the traveller's route.
- `get_local_tips` — etiquette, customs, and on-the-ground advice.
- `search_travel_knowledge` — general destination knowledge and advisories.
- `get_climate` — typical weather for the destination and season.
- `get_packing` — a packing list keyed to destination and season.

## Procedure

1. Call `get_visa` for the origin→destination and note requirements, documents, and any
   timeframes, each cited.
2. Call `get_climate` for the destination and the travel month(s) to describe the
   season.
3. Call `get_local_tips` and `search_travel_knowledge` for etiquette, safety, and
   practical advice relevant to this trip.
4. Call `get_packing` and summarise what to bring for that climate.

## What belongs in `/research/entry-and-season.md`

- `# Entry & Season` H1.
- H2 **Entry**: visa/entry rules with documents and timing, each cited to `get_visa`.
- H2 **Season**: typical conditions for the travel window, cited to `get_climate`.
- H2 **Local tips**: etiquette/safety points, cited.
- H2 **Packing**: a short list, cited to `get_packing`.

## When a tool returns nothing

If a tool returns nothing (e.g. no visa record for the route), write the section with
what was queried and "No data returned (get_visa)." Do not state an entry rule that no
tool confirmed — an unconfirmed visa claim can mislead a traveller.

## Never invent

Never write a visa rule, fee, timeframe, or climate figure that a tool did not return.
Entry requirements stated from memory are unsafe; every claim names its tool.
