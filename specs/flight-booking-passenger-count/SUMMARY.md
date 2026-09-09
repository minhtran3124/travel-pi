# flight-booking-passenger-count — Summary

Lane: high-risk
Confidence: high
Reason: one block-mode hard gate — public-contract (a new field on the flight book request and on the stored booking detail, and a changed `total_price` for the same inputs). Nothing else fires: no auth, no migration, no external provider, one domain.
Flags: public-contract, existing-behavior
Affects: `FlightBookingRequest` / `FlightBookingDetails` (`apps/api/app/schemas/flight.py`, `schemas/booking.py`), `BookingService.book_flight`, the `book_flight` agent tool, booking prompt
Input-type: change request
Route: writing-plans → subagent-driven-development, continuing on `feat/close-product-loop-s1-booking-ui`. Brainstorming and xia2 skipped deliberately — see Rationale; branch choice explained there too.
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

cho van de so ghe cua dat ve di, solution don gian thoi. Vi chung ta ko focus vao he thong booking flight, chi la cong cu dat ve cua chatbot thoi

Context this follows from: PR #167 left a known limitation. A flight booking always creates **one
seat at the one-adult fare**, because `FlightBookingRequest` carries no passenger count and
`BookingService.book_flight` sets `total_price=flight.price` flat
(`app/services/booking_service.py:380`). A traveller who asks the assistant for three seats gets
one, and the trip's `booked_total` understates the real spend by two thirds. The web page that used
to warn about this is gone, and the assistant does not say it either.

The instruction is explicit that this is a chatbot booking tool, not a booking system, so the
solution stays small.

## What changed

A flight booking is priced for the seats actually asked for. `FlightBookingRequest` and
`FlightBookingDetails` carry `passengers` (default 1, `ge=1`), `BookingService.book_flight`
multiplies the fare by it, and `book_flight` takes it as a model-supplied argument so the assistant
can pass what the traveller said. Booking prompt v10 tells it to ask, and that one call books every
seat rather than being repeated per traveller.

Two commits: `bee98f4` (contract and price) and `76b44c1` (tool and prompt).

### Rationale

The shape is not an open question: **hotels already solve this**. `book_hotel` takes `rooms`,
`adults` and `children`, stores them on `HotelBookingDetails`, and computes
`total_price = price_per_night × nights × rooms` (`booking_service.py:412-479`). Flights mirror
that with a single `passengers` field, and the parallel makes the review trivial.

No migration is needed: `Booking.details` is already a JSON column holding a tagged union, so a new
field on `FlightBookingDetails` costs nothing at the schema level, and `total_price` is an existing
column.

The work continues on `feat/close-product-loop-s1-booking-ui` rather than a fresh branch off `main`.
That branch is where this limitation was found and recorded, its PR (#167) is open and green, and
branching off `main` instead would edit a `flight_tools.py` and a prompt set that do not yet contain
that PR's changes — a guaranteed conflict for no benefit.

Brainstorming is skipped because there is no design fork — one viable approach, already precedented
in the same file. xia2 is skipped because the relevant code was read end to end during the session
that produced this limitation, and the citations are in the Intent above. Per
`rules/orchestration.md`, plan-ahead artifacts scale by **signal**, not by lane; the lane here is
procedural (a public-contract gate fired on an additive field), while the change itself is four
files and a handful of tests.

### Alternatives considered

- **Leave it and have the assistant say "one seat only".** Rejected: it makes the tool visibly
  worse than the hotel tool it sits next to, and the user asked for the fix.
- **Book N separate reservations, one per passenger.** Rejected: N confirmation codes for one trip,
  N rows in the Bookings tab, and no way to cancel them as a unit.
- **Also refuse when `passengers > seats_available`.** `Flight.seats_available` exists
  (`schemas/flight.py:68`) and the hotel path does guard availability with a 409, so it would be the
  consistent thing to do. **Excluded — the user ruled it out explicitly** ("Ko can check ghe con hay
  het dau"): it adds a new error path against simulated inventory that never decrements, and this is
  a chatbot tool, not a booking system. A flight booking will therefore accept any passenger count
  the traveller asks for, regardless of the seats the search reported.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| N seats, N × fare | `cd apps/api && ../../.venv/bin/python -m pytest "tests/api/booking/test_flight_passengers.py::test_books_n_seats_at_n_times_the_fare" -q` | 0 | detail records the count | SC-1 |
| Default is one seat | `cd apps/api && ../../.venv/bin/python -m pytest "tests/api/booking/test_flight_passengers.py::test_defaults_to_one_seat_at_the_single_fare" -q` | 0 | today's behaviour preserved | SC-2 |
| Below 1 rejected | `cd apps/api && ../../.venv/bin/python -m pytest "tests/api/booking/test_flight_passengers.py::test_invalid_passenger_count_is_422" -q` | 0 | 422 from `ge=1` | SC-3 |
| Assistant can pass it | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_passengers.py -q` | 0 | tool invoked the way the graph does | SC-4 |
| Booking, replay, trip link, premium gate | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_bookings.py tests/api/booking/test_booking_trip_link.py tests/api/booking/test_premium_gate.py -q -p no:randomly` | 0 | 52 passed, ~24s | SC-5 |
| Prompt registry and `active.yaml` | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts tests/api/prompts/test_prompt_registry_helpers.py -q -p no:randomly` | 0 | v10 kept every pinned rule | SC-6 |
| Hotels untouched | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/hotel -q -p no:randomly` | 0 | | SC-7 |
| Backend lint | `cd apps/api && ../../.venv/bin/ruff check app` | 0 | All checks passed | SC-8 |
| Task 1.1 Verify as written | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_flight_passengers.py tests/api/booking/test_bookings.py tests/api/booking/test_booking_trip_link.py tests/api/booking/test_premium_gate.py -q -p no:randomly` | 0 | 55 passed | |
| Task 2.1 Verify as written | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_passengers.py tests/tools/test_booking_trip_id.py tests/prompts tests/api/prompts/test_prompt_registry_helpers.py tests/api/hotel -q -p no:randomly && ../../.venv/bin/ruff check app` | 0 | 114 passed | |

### Not auto-verified

- ~~The assistant actually asking for a passenger count in a live conversation~~ — **now verified in
  a browser.** See `uat/`: asked for three seats in chat, the assistant stated "Passengers: 3,
  Total: USD 151.83" before booking, the tool call logged `passengers = 3`, and the row holds
  `total_price` 151.83 with `details.passengers` 3 at 50.61 a seat, stamped with the trip.
- ~~`apps/web/src/lib/api/schema.d.ts` is now stale.~~ **Regenerated in `fff9e4e`**, because showing
  the seat count required the frontend to read the field.
- **The full `tests/api/booking` directory** — not run here. It sits at about 60s, over the limit a
  re-runnable row must meet, so two of its files are left to `finishing-a-development-branch`.

### Rollback

- `git revert 76b44c1 bee98f4`
- No migration to reverse: the field lives in the existing `Booking.details` JSON column. Bookings
  written before the revert keep their stored `total_price`, which stays correct for the seats they
  recorded.

### Follow-up, raised and then approved

The Bookings tab showed the party total but not the party, so a three-seat row read as one seat at
triple the fare. Raised for a decision, approved, and done in `fff9e4e`: the flight subline now
carries a plural seat count beside the departure and passenger name, mirroring how the hotel subline
already carries nights and rooms. It shows only above one seat — single-seat is the common case, and
bookings written before the field have nothing to show.

That commit also regenerated `apps/web/src/lib/api/schema.d.ts`, which closes the staleness this
summary had listed as deliberate: the frontend could not read `passengers` until the generated type
had it. The diff is exactly the new field and the docstring beside it.

### Harness-Delta

- none
