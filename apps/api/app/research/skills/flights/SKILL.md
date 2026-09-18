---
name: flights
description: Operating procedure for researching the flights dimension of a trip and writing /research/flights.md. Activate when tasked with the flights leg of a dossier — it explains how to use search_flights and resolve_date, what a flight entry must record (offer id, route, times, price, cabin), what to do when no offers come back, and the rule never to invent an offer id, price, or date. Read it before searching flights or writing the flights file.
---

# Skill: flights

Research the trip's flights and write `/research/flights.md`. Follow `dossier-format`
for the file path, headings, and the citation rule.

## Tools

- `search_flights` — the only source of flight offers. Every offer id and price comes
  from here.
- `resolve_date` — turn a verbatim date phrase ("next Friday", "15/8") into a concrete
  date before searching. Never compute a date yourself.

## Procedure

1. Read the trip summary and the traveller's ask from the overview / the task prompt:
   origin, destination, dates, party size, cabin.
2. If a date is expressed in words, call `resolve_date` first; cite it.
3. Call `search_flights` with the resolved parameters. Repeat with a sensible variation
   (nearby dates, other cabin) only if it helps the traveller decide — stay within the
   subagent tool-round budget.
4. Record each offer you keep: **offer id**, origin→destination, depart/arrive times,
   duration, stops, cabin, and price. Every one of these is followed by `(search_flights)`.
5. Recommend a shortlist (2–4 offers) and say briefly why (cheapest, fastest, best
   time), citing the tool for every figure.

## What belongs in `/research/flights.md`

- `# Flights` H1.
- The search parameters actually used (origin, destination, resolved dates, party).
- A list or table of offers, each with its **offer id** and price, each cited.
- A short recommendation naming the offer ids to carry into the proposal.

## When a tool returns nothing

If `search_flights` returns no offers, still write the file: state the parameters
searched and "No offers returned (search_flights)." Do not fabricate an alternative.

## Never invent

Never write a flight offer id, price, time, or date that a tool did not return. An id
that does not come from `search_flights` cannot go into `/plan/proposal.json` and will
fail `validate_proposal`.
