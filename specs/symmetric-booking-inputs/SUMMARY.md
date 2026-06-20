---
slug: symmetric-booking-inputs
lane: normal
confidence: high
created: 2026-06-20
owner: Minh Tran
---

# Symmetric booking inputs — accept `flight_id` on `POST /flights/book`

## Intake

```text
Lane: normal
Confidence: high
Reason: 2 flags (public-contract request-shape change, existing test-covered endpoint); no hard gate — the flight-identity invariant is preserved, not weakened.
Flags: public-contract, existing-behavior
Affects: FlightBookingRequest (app/schemas/flight.py) → POST /flights/book request contract; booking_service.book_flight
Input-type: Change request
Route: normal → /using-git-worktrees → /subagent-driven-development
Escalate: no
```

### Intent

> "9. ⬜ Symmetric booking inputs" from AGENT_IMPROVEMENTS.md:
>
> `POST /flights/book` still takes flight_number + route + date; `POST /hotels/book` takes hotel_id. Make `flight_id` accepted as an alternative on flight booking so an agent can do `search → pick id → book` without unpacking the ID. (`FlightBookingRequest` in `app/schemas/flight.py` has no `flight_id` field today.)

## Rationale

`POST /hotels/book` takes a single `hotel_id`; `POST /flights/book` instead
requires `flight_number + origin + destination + departure_date`. An agent that
just ran `GET /flights/search` holds each result's `id`, but today it must
unpack that id back into the route triple to book — extra steps and a chance to
derail. The resolver already exists: `flight_service.find_flight_by_id(flight_id)`
(`app/services/flight_service.py:216`) reverses a flight id back to
`(origin, destination, departure_date)` via the persisted `flight_index`. So
this is additive plumbing, not new capability.

**Chosen shape:** add an optional `flight_id` to `FlightBookingRequest`; make the
four identification fields optional; add a model-level validator that requires
**exactly one** identification mode — `flight_id`, *or* the
`flight_number + origin + destination + departure_date` quad. `book_flight`
branches on which is present. This keeps the existing path byte-for-byte for
current callers and preserves the invariant "you must fully identify one real
flight" — the validation is restructured, not weakened.

## Alternatives

- **Add `flight_id` as a pure extra field, all four legacy fields still
  required.** Rejected — defeats the point (#9 asks for an *alternative* so the
  agent need not unpack the id).
- **New endpoint `POST /flights/book-by-id`.** Rejected — duplicates the booking
  path and adds a public route (genuine new-endpoint hard gate) for no benefit;
  one request schema with a cross-field rule is simpler.

## Lane reasoning (why normal, not high-risk)

- Flags: **public-contract** (request body shape changes — client-visible) and
  **existing-behavior** (modifies a test-covered endpoint). 2 flags → normal.
- **No hard gate.** "Weakening validation" does *not* fire: making the route
  fields conditionally-optional is paired with a cross-field validator that
  still demands one complete flight identity, so net validation strength is
  unchanged. No auth/authz/migration/external-provider/high-blast surface. No
  new `@router` decorator (the endpoint already exists), so the
  `risk-corroboration` public-contract path trigger should not fire either.
- Confidence **high**: single clear interpretation; the only open choice
  (conflict handling when both modes are sent) has a sensible default —
  reject-on-both via the validator. Proceed autonomously, notify-and-proceed.

## Assumptions

- If both `flight_id` and the route quad are supplied, the request is **rejected
  (422)** by the validator rather than silently preferring one. (Default; flag
  if a "must agree / flight_id wins" behavior is preferred instead.)
- `find_flight_by_id` returning `None` (unknown/expired id) maps to the same
  `NotFoundError`/404 as the unknown-flight_number path, with a `hint` pointing
  back to `GET /flights/search`.

### Deviations

- Rule 3 — re-added the `model_validator` pydantic import after `ruff-on-edit`
  auto-removed it during the window it was momentarily unused. `app/schemas/flight.py`.
- Rule 1 — correctness review caught: blank-string identifiers (`flight_id=""`
  or empty quad) slipped past the `is not None` checks → misleading 404 instead
  of 422. Switched validator + service branch to truthiness (`bool()`/`all()`/
  `if request.flight_id:`) and added `test_book_flight_blank_identifiers_returns_422`.
  `app/schemas/flight.py`, `app/services/booking_service.py`.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| Lint | `ruff check app` | 0 | clean |
| Flight tests | `python -m pytest tests/api/flight/test_flights.py -q` | 0 | 52 passed (5 new: by-id 200, by-id≡quad, both→422, unknown-id→404, blank→422) |
| Full suite | `python -m pytest -q` | 0 | 672 passed (was 667) |

Cross-engine Postgres parity (`make test-docker`) not run — change is request-validation
+ service-resolution only, no ORM/schema/migration surface, so SQLite coverage is
representative. The forward-ref return annotation is a string literal, safe under Docker's
eager-annotation Python 3.12.

### Rollback

- Revert code: `git revert <sha>` (single commit; no migration, no data change).

## Status Log

- 2026-06-20 — intake complete; lane=normal, confidence=high, PROCEED. Routed to
  normal path (worktree → subagent-driven-development). PLAN.md warranted
  (touches schema + service + tests, >2 files).
