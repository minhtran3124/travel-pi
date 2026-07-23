# PRODUCT.md — Travel Planner web (`apps/web`)

## What it is

The Next.js frontend for the Travel Planner agent. Users plan trips (itinerary,
budget, expenses, shortlist), browse/save places, manage bookings, and converse
with an AI travel co-pilot (streaming chat with human-in-the-loop approvals).
Backend is a FastAPI mock (`apps/api`) reached through the `/api/be/*` proxy;
the agent streams over `/agent/stream`.

## Who uses it

A traveler planning a trip on desktop or mobile web — exploring, comparing, and
committing plans, often mid-task and quickly. The UI should stay calm and
legible, get out of the way, and make the next action obvious.

## Register

**Product** — design serves the task, not the other way round. Clarity,
scannability, and fast affordances beat expressive flourish. One accent, used
deliberately. Full visual system in [DESIGN.md](./DESIGN.md).

## Surfaces

- `/trips` — trip list + create.
- `/trips/[id]` — trip detail: Itinerary · Budget · Expenses · Shortlist tabs.
- `/places` — catalog search + saved places.
- `/bookings` — bookings ledger with client-side filter/sort.
- Global chat co-pilot (FAB → panel) on every route.

## Principles

- **Primary = ink, accent = lime.** Near-black primary actions; chartreuse only
  for active/affordance cues so it keeps its signal.
- **Restrained color.** White surfaces, hairline borders, soft shadows.
- **Legibility first.** Body text holds AA contrast; placeholders use the darker
  muted, not faint gray.
- **Optimistic, recoverable.** Mutations update immediately and roll back on
  error; 409 conflicts surface as friendly notices, never crashes.
