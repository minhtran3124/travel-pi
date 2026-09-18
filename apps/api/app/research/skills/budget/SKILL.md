---
name: budget
description: Operating procedure for researching the trip budget and writing /research/budget.md. Activate when tasked with the budget dimension of a dossier — it explains how to use get_trip_budget, estimate_trip_budget, and expense_summary to read any existing caps, estimate costs, and roll up spending, how to keep totals consistent with the flights/stays/day figures, what to do when a tool returns nothing, and the rule never to invent a number. Read it before researching the budget or writing that file.
---

# Skill: budget

Research the trip's money and write `/research/budget.md`. Follow `dossier-format` for
the path, headings, and the citation rule.

## Tools

- `get_trip_budget` — the caps the traveller already set on this trip, if any.
- `estimate_trip_budget` — a modelled estimate for the trip's shape.
- `expense_summary` — what has already been spent/recorded on this trip.

## Procedure

1. Call `get_trip_budget` to read existing caps. If a cap is set, every total in the
   dossier must respect it; flag any dimension that would exceed it.
2. Call `estimate_trip_budget` for a modelled cost and record the breakdown, cited.
3. Call `expense_summary` for money already spent, and show remaining headroom.
4. Reconcile with the other dimensions: the flight prices in `/research/flights.md` and
   the nightly rates in `/research/stays.md` are the authoritative line items — reference
   them (and their tools) rather than re-deriving prices here.

## What belongs in `/research/budget.md`

- `# Budget` H1.
- H2 **Caps**: the trip's set budget, cited to `get_trip_budget` (or "no cap set").
- H2 **Estimate**: the modelled breakdown, cited to `estimate_trip_budget`.
- H2 **Spent so far**: from `expense_summary`, with remaining headroom.
- A bottom-line total that respects the cap when one is set.

## When a tool returns nothing

If no budget is set, state "No cap set (get_trip_budget)" and proceed with the estimate.
If there are no expenses yet, say so. Do not invent a cap the traveller never set.

## Never invent

Never write a cap, estimate, or spent figure that a tool did not return, and never
present a price for flights or hotels that did not come from `search_flights` /
`search_hotels`. The proposal's `budget_estimate` is built from these cited figures.
