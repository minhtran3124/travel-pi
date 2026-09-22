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
   destination, dates, party size, cabin. **The origin comes only from the request's
   `Departing from:` line** — the traveller's own words. Never take it from the
   destination, the traveller's profile, a nearby city or a "likely" hub.
   - **No `Departing from:` line → do not call `search_flights`.** Write the file with
     "Departure point not provided — ask the traveller where they are travelling from
     before searching flights." and leave the proposal's `flights` empty.
   - Turn the stated place into its IATA code for `search_flights` (Saigon / Ho Chi Minh
     City → `SGN`); the destination is the trip city's airport (Phu Quoc → `PQC`). If the
     place has several airports or you are unsure of the code, say which you chose and
     why in the file.
2. If a date is expressed in words, call `resolve_date` first; cite it.
3. Call `search_flights` **once per leg, one-way**: the outbound leg, then the return leg
   with origin and destination swapped and the return date as `departure_date`. A
   round-trip call lists only the outbound offers' ids, so it cannot give you a return
   `offer_id`. Repeat with a sensible variation (nearby dates, other cabin) only if it
   helps the traveller decide — stay within the subagent tool-round budget.
4. Record each offer you keep: **offer id** — the value after `offer_id` in the tool's
   "Ids for the proposal" list, never the flight number (`VN422` is not an offer id) —
   origin→destination, depart/arrive times,
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

Never invent a departure point either: a route the traveller did not give is a guess,
and a flight search on a guessed route is worse than none.

Never write a flight offer id, price, time, or date that a tool did not return. An id
that does not come from `search_flights` cannot go into `/plan/proposal.json` and will
fail `validate_proposal`.
