---
slug: flight-booking-passenger-count
status: shipped
owner: Minh Tran
created: 2026-09-09
---

# Flight bookings carry a passenger count

## 1. Motivation

A flight booking always creates one seat at the one-adult fare: `FlightBookingRequest` has no
passenger count and `BookingService.book_flight` sets `total_price=flight.price` flat
(`app/services/booking_service.py:380`). A traveller who asks the assistant for three seats gets
one, and the trip's `booked_total` understates the spend by two thirds.

Hotels already solve this. `HotelBookingRequest` takes `rooms` (`schemas/hotel.py:211`), stores it
on the booking detail, and computes `price_per_night × nights × rooms`
(`booking_service.py:469`). Flights mirror that with one field.

Intake: `specs/flight-booking-passenger-count/SUMMARY.md` (lane `high-risk` because the
public-contract gate fires on the new field; the change itself is four files).

## 2. Non-goals

- **No seat-availability check.** `Flight.seats_available` exists and the hotel path guards with a
  409, but the user ruled this out: the inventory is simulated and never decrements. A booking
  accepts any passenger count.
- No migration. `Booking.details` is already a JSON column holding a tagged union.
- No per-passenger names. One booking, one lead passenger, N seats — the same shape hotels use for
  rooms.
- No change to hotel booking, to the premium gate, or to `trip_id` stamping.
- No web UI change. `/flights` is browse-only and has no booking control.
- **`apps/web/src/lib/api/schema.d.ts` is left stale on purpose.** It is a checked-in artifact of
  `pnpm gen:api` and contains `FlightBookingRequest`, so it drifts the moment this lands. No web
  code calls `/flights/book` any more and no CI gate checks the drift, so regenerating it would be
  noise; the next slice that touches the web client regenerates it.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | Booking N passengers charges N times the fare, and the booking records N | `cd apps/api && ../../.venv/bin/python -m pytest "tests/api/booking/test_flight_passengers.py::test_books_n_seats_at_n_times_the_fare" -q` | exit 0 |
| SC-2 | Omitting the field still books one seat at the single fare, as before | `cd apps/api && ../../.venv/bin/python -m pytest "tests/api/booking/test_flight_passengers.py::test_defaults_to_one_seat_at_the_single_fare" -q` | exit 0 |
| SC-3 | A passenger count below 1 is rejected by validation | `cd apps/api && ../../.venv/bin/python -m pytest "tests/api/booking/test_flight_passengers.py::test_invalid_passenger_count_is_422" -q` | exit 0 |
| SC-4 | The assistant can pass a passenger count through the booking tool | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_passengers.py -q` | exit 0 |
| SC-5 | Existing flight booking, replay, trip-link and premium-gate behaviour still holds | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_bookings.py tests/api/booking/test_booking_trip_link.py tests/api/booking/test_premium_gate.py -q -p no:randomly` | exit 0 |
| SC-6 | The prompt registry still loads, its pinned rules survive v10, and `active.yaml` stays consistent | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts tests/api/prompts/test_prompt_registry_helpers.py -q -p no:randomly` | exit 0 |
| SC-7 | Hotel booking is untouched | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/hotel -q -p no:randomly` | exit 0 |
| SC-8 | Backend lint is clean | `cd apps/api && ../../.venv/bin/ruff check app` | exit 0 |

Every check above is named by exact node id or by a file/directory that exists independently of
this change, so a mistyped test name fails the row instead of silently selecting nothing. The full
`tests/api/booking` directory runs about 60s, at the guardrail, so the two expensive files it also
contains — `test_booking_ownership.py` and `test_booking_list_trip_filter.py` — are left to
`finishing-a-development-branch` rather than pinned here.

## Global Constraints

- **Branch.** Continue on `feat/close-product-loop-s1-booking-ui`, where this limitation was found
  and recorded. Do not branch off `main`: it lacks that branch's `flight_tools.py` and prompt set,
  so the same edits would conflict for no benefit.
- **Mirror hotels, do not invent.** `rooms` on `HotelBookingRequest` (`schemas/hotel.py:211`) is the
  shape to copy: `int`, a default, `ge=1`, stored on the booking detail, multiplied into
  `total_price` server-side.
- **The fare stays server-side.** `total_price` is computed from the resolved flight, never sent by
  the client. Multiplying by the passenger count must not change that.
- **No new error path.** Do not add a seats check; do not add a 409.
- **Do not touch** `app/agents/`, `app/mcp/`, `apps/web/`, hotel booking, or the premium gate.
- The ruff-on-edit hook deletes an import added before its first use — add an import and its first
  usage in the same edit.
- Run backend commands from `apps/api` with `../../.venv/bin/python`.
- A prompt edit does not reach a running server: force a rebuild with
  `docker exec api-api-1 touch app/main.py`.
- **Never run the whole suite in a task Verify.** The full run happens at
  `finishing-a-development-branch`.

## 4. Tasks

### Task 1.1 — `passengers` on the flight booking contract (wave 1)

- **Files:** apps/api/app/schemas/flight.py, apps/api/app/schemas/booking.py, apps/api/app/services/booking_service.py, apps/api/tests/api/booking/test_flight_passengers.py
- **Action:** Write `tests/api/booking/test_flight_passengers.py` first, with exactly these three
  test names, because the success criteria select them by node id and a different name fails the
  row rather than silently selecting nothing:
  `test_books_n_seats_at_n_times_the_fare` — booking 3 passengers returns
  `total_price == 3 × fare` and a booking whose detail records 3;
  `test_defaults_to_one_seat_at_the_single_fare` — omitting the field books 1 seat at the single
  fare, reproducing today's behaviour;
  `test_invalid_passenger_count_is_422` — `passengers=0` is rejected by validation.
  Then add `passengers: int = Field(default=1, ge=1, ...)` to `FlightBookingRequest`, mirroring
  `rooms` on `HotelBookingRequest` (`schemas/hotel.py:211`) in shape and docstring style; add the
  same field to `FlightBookingDetails` so the booking records what was bought; and multiply it into
  `total_price` in `BookingService.book_flight` (`booking_service.py:380`), the way the hotel path
  multiplies by `rooms` at `:469`. Update the `FlightBookingRequest` class docstring, which
  currently describes the fare as taken from the flight — it is now fare × passengers.
  Do not add a seats-availability check.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_flight_passengers.py tests/api/booking/test_bookings.py tests/api/booking/test_booking_trip_link.py tests/api/booking/test_premium_gate.py -q -p no:randomly`
- **Done:** Booking N passengers stores N on the detail and charges N × fare; omitting the field
  reproduces today's single-seat behaviour; a count below 1 is a 422; the existing booking, replay
  and trip-link tests still pass, and so does the premium gate — the only test that drives
  `POST /flights/book` through the tier check, which is the route whose request schema this task
  changes (52 tests today, ~24s).
- **Criteria:** SC-1, SC-2, SC-3, SC-5
- **Interfaces:** Consumes the existing flight fare resolution. Produces `passengers` on `apps/api/app/schemas/flight.py` and on `apps/api/app/schemas/booking.py`.

### Task 2.1 — The assistant can book more than one seat (wave 2)

- **Files:** apps/api/app/tools/flight_tools.py, apps/api/app/prompts/booking/v10.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/tests/tools/test_booking_passengers.py
- **Action:** Write `tests/tools/test_booking_passengers.py` first: invoking `book_flight` the way
  the graph does, with a passenger count, produces a booking recording it and priced for it; with
  no count, one seat.
  Then add `passengers` to `BookFlightArgs` and to the `book_flight` signature as a **model-supplied**
  argument — unlike `user_id` and `trip_id` it is not injected, because the traveller states it —
  defaulting to 1, and pass it into the request the tool builds.
  Copy `booking/v9.md` to `v10.md` and state that the passenger count is one of the values that must
  be obtained explicitly from the traveller and passed to `book_flight`, and that one booking covers
  all seats rather than being repeated per traveller. It already sits under the "No default-with-confirm"
  rule as "party size", so this is making an existing rule reachable, not adding one. Point
  `active.yaml` at `booking: 10` and add a `CHANGELOG.md` entry in the existing style.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_passengers.py tests/tools/test_booking_trip_id.py tests/prompts tests/api/prompts/test_prompt_registry_helpers.py tests/api/hotel -q -p no:randomly && ../../.venv/bin/ruff check app`
- **Done:** `book_flight` accepts a passenger count from the model and the resulting booking records
  and prices it; `tests/prompts` still passes, so v10 kept every rule those tests pin and
  `active.yaml` resolves; hotel booking and lint are untouched.
  The Verify names files rather than directories in two places, on purpose. All of `tests/tools`
  would pull in two offline-estimate tests in `test_routing_tools.py` that fail whenever the network
  is up; all of `tests/api/prompts` would pull in fourteen dashboard tests that 401 because
  `apps/api/.env` sets the dashboard credentials. Both predate this branch and would make a passing
  task look failed. `test_prompt_registry_helpers.py` is named individually because it is the one
  file there that actually reads `active.yaml`.
- **Criteria:** SC-4, SC-6, SC-7, SC-8
- **Interfaces:** Consumes `passengers` from Task 1.1. Produces the argument on `apps/api/app/tools/flight_tools.py` and `apps/api/app/prompts/booking/v10.md`.

## 5. Risks

- **The fare is per adult, and nothing says so on the booking.** Multiplying is right for this
  simulated inventory, but a real airline prices per passenger type. Out of scope, and the
  simulation has one fare.
- **`booked_total` will move for new bookings only.** Existing single-seat bookings keep their
  stored `total_price`; nothing backfills, and nothing should.
- **Prompt v10 does not reach the running dev server on its own.** The registry is a singleton and
  the graph is built at lifespan startup; `touch app/main.py` in the container after the change.
- The two `tests/tools/test_routing_tools.py` offline-estimate failures predate this work and fail
  whenever the network is up. Task 2.1's Verify is scoped around them deliberately; do not "fix"
  them here.

## 6. Status Log

| Date | Event |
|---|---|
| 2026-09-09 | Plan written from the intake SUMMARY. No design or research brief: no design fork, and the precedent is one file away. Status `proposed`. |
| 2026-09-09 | Wave 1 complete: task 1.1; commit bee98f4. Verify re-run by the controller: 55 passed. |
| 2026-09-09 | Wave 2 complete: task 2.1; commit 76b44c1. Verify re-run by the controller: 114 passed, ruff clean. All eight success criteria exit 0. |
| 2026-09-09 | Independent review: four issues fixed. Task 2.1's Verify could not exit 0 (it included two pre-existing network-dependent failures) and ran 107s; the prompt bump had test callers in `tests/prompts` that no task ran; `tests/api/booking` sits at the 60s guardrail; `rooms` is at `hotel.py:211`, not `:212`. Task 3.1 folded into 2.1 — it was a gate, not a task. Criteria now select by exact node id so a mistyped test name fails instead of selecting nothing. |
