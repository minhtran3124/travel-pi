---
problem_type: bug
module: agent/tools
tags: langgraph, booking, pii, guardrails, alembic, dev-database, tool-output, search_flights, uat
severity: critical
applicable_when: An agent tool path that passes every unit test cannot be completed by a real user in the browser — especially a booking/write tool that requires a field the model must obtain from conversation, or that needs an identifier produced by a sibling search tool.
affects:
  - apps/api/app/agents/guardrails.py
  - apps/api/app/tools/flight_tools.py
  - apps/api/app/prompts/booking/v9.md
supersedes: null
confidence: high
confirmed_at: 2026-09-09
---
## Problem

After slice S1 of `close-product-loop` shipped green — full backend suite, per-task
reviews, CI e2e — booking a flight through the chatbot was still impossible end to end.
Every automated check passed. A browser UAT session against the dev stack failed at three
different points in sequence, each one only visible once the previous was cleared.

## Root Cause

Three independent defects stacked on the same path:

1. **The dev Postgres never had the migration applied.** The long-lived Docker database
   pre-dates the branch; `lifespan`'s `create_all` adds new *tables* but never new
   *columns*, so the new booking columns were silently absent. Tests run against a fresh
   SQLite file and therefore always saw the current schema.
2. **The PII guardrail redacted the one field the tool required.** `redact_pii` runs as a
   graph entry node and masked every email in the user's turn. The booking tools require
   an email. The model asked for it, the user typed it, the guardrail removed it, and the
   model asked again — an unbreakable loop that no test could see, because tests invoke
   tools directly and skip the entry node.
3. **The identifier the tool needs never reached the model.** `search_flights` summarised
   results by flight number, route and date; the row `id` that `book_flight` takes was
   dropped from the model-facing text. The tool's schema was satisfiable in principle and
   unsatisfiable in practice.

The common shape: each defect lives in the seam *between* two components that are each
tested in isolation. Unit tests cover the tool. Node tests cover the guardrail. Nothing
covered the sentence "a user, in a browser, on the dev database, completes a booking".

## Fix

- Applied the migration to the dev Postgres (`alembic upgrade head` inside the container),
  and confirmed `alembic heads` resolved to a single head first.
- Narrowed `redact_pii` so it no longer masks email; card numbers are still masked. This
  is a deliberate, user-approved privacy trade-off, recorded in the function's docstring:
  real emails now flow into the model, the checkpointer and conversation history.
- Reframed the booking prompt (v9) to book by `flight_number` + route + date rather than
  by the opaque `id`, so the model books with the identifiers it can actually see.
- Added a v8 step where the assistant offers the signed-in account email and asks for a
  replacement only if declined, so the email round-trip usually costs zero turns.

## Regression Test

None added at the unit level, deliberately — none of the three defects is reachable from
the offline suite. The re-runnable proof is the browser UAT script under
`specs/<slug>/uat/run-uat.mjs`, which drives the real chat against the dev stack and
screenshots each case. Treat UAT as the regression test for any agent path whose
completion depends on runtime state (applied schema, entry-node transforms, model-facing
tool text).

## Prevention

- After any ORM/schema change, run the migration against the **dev** database, not only
  the test database. A green suite says nothing about a long-lived database.
- Before shipping a tool that requires a field the user must supply, trace that field
  through every graph entry node. A guardrail that transforms user text can make a
  required argument permanently unreachable.
- A tool's arguments must be derivable from what the model can *read*. When tool A
  produces an identifier that tool B consumes, the identifier must appear in A's
  model-facing summary, not only in its return payload.
- Run browser UAT before declaring a user-facing agent path done.

## Related

- docs/solutions/agent/langgraph-thread-reset-and-prompt-reload.md
- docs/solutions/agent/concierge-hotel-tool-choice.md
