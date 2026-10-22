---
slug: gh-194-duplicate-booking-warning
status: shipped
owner: Minh Tran
created: 2026-09-14
---

# gh-194 — Warn on duplicate-intent bookings (agent path)

## 1. Motivation

A traveller who repeats "book it" in a new turn (stream dropped) or opens a fresh chat and asks
again gets a second identical booking with no signal. The per-turn idempotency key (#193) must
not block this — it is a genuinely new request — so the agent needs a "possible duplicate"
warning it relays to the traveller, with an explicit override to book anyway.

Decisions (ESCALATIONS.md, user, 2026-09-14): E001 **C** — shared logic in `BookingService`
behind an opt-in `check_duplicate` flag that only the agent tools pass; REST unchanged.
E002 **A** — flight = same owner + same flight row (`reference_id`) + same `passengers`;
hotel = same owner + same hotel + exact same `check_in` + `check_out`; cancelled bookings
never count. E003 **A** — surfaced via the tool result only; the model asks, and a call with
`allow_duplicate=True` proceeds.

## 2. Non-goals

- REST `POST /flights/book` and `POST /hotels/book` behaviour and schema (they keep calling the
  service with the default `check_duplicate=False`).
- The HITL plan draft, prompts, `active.yaml`, `SYSTEM_COPY` — no prompt or copy change.
- MCP — destructive tools are already excluded (`app/mcp/server.py:61`).
- Schema or migration — `bookings` already has `user_id`, `type`, `reference_id`, `status`, `details`.
- Overlapping hotel date ranges (E002 option C was not chosen).

## Global Constraints

- All paths below are relative to the worktree root `/Users/minhtran/Documents/minhtran3124/developer/travel-pi-gh-194`. Run BE commands from `apps/api/`; the venv lives in the MAIN checkout: `/Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python`.
- No `apps/api/.env` exists in the worktree — keep it that way (tests use FakeLLM + SQLite).
- Order inside `book_flight` / `book_hotel` is load-bearing: `_replay` (idempotency) runs FIRST, so a same-turn revise re-run still returns the original booking instead of tripping the duplicate check against itself. The duplicate check runs after the flight/hotel is resolved and BEFORE the hotel availability check and the insert.
- `check_duplicate` defaults to `False`; REST routes are not edited.
- The duplicate error is a `ConflictError` subclass (`DuplicateBookingError`) so the existing `except AppError → tool_error(e)` path relays it to the model unchanged; `detail` names the existing booking's `confirmation_code` (fallback `id`), the date(s) and passenger/room count; `hint` says to ask the traveller and call again with `allow_duplicate=true` only if they confirm.
- `allow_duplicate` is NOT part of the idempotency-key args dict (the key identifies the booking content; including the override would let a revise re-run with a flipped flag create a second row).
- Never log PII (passenger/guest name, email, phone). Match surrounding docstring style (`:param:` / `:return:`).
- Implement only — do not `git commit`; the controller serializes commits. Stage nothing.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
| --- | --- | --- | --- |
| SC-1 | With `check_duplicate=True`, booking the same flight (same passengers) or the same hotel + exact dates for the same owner raises `DuplicateBookingError` naming the existing booking, and stores no new row | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate.py -q -k raises` | exit 0 |
| SC-2 | Not flagged: cancelled booking, different passenger count, different hotel dates, another owner, or `check_duplicate=False` (the REST default) | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate.py -q -k not_flagged` | exit 0 |
| SC-3 | Agent `book_flight` / `book_hotel` on a new turn for an identical active booking returns a ToolException mentioning the existing confirmation code and `allow_duplicate`, and creates no row; `allow_duplicate=True` books a second row | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/tools/test_booking_duplicate_tools.py -q` | exit 0 |
| SC-4 | REST booking contract unchanged — posting the same flight/hotel twice still creates two bookings | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/api/booking tests/api/flight tests/api/hotel -q` | exit 0 |
| SC-5 | Existing booking-tool tests (idempotency, passengers, owner, trip_id, cancel) still pass | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/tools -q` | exit 0 |
| SC-6 | Lint clean on changed code | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/ruff check app tests/services/test_booking_duplicate.py tests/tools` | exit 0 |

## 4. Tasks

### Task 1.1 — Opt-in duplicate check in BookingService (wave 1)

- **Files:** apps/api/app/exceptions.py, apps/api/app/repositories/booking.py, apps/api/app/services/booking_service.py, apps/api/tests/services/test_booking_duplicate.py
- **Action:** Add `DuplicateBookingError(ConflictError)` in `exceptions.py` carrying the existing
  `Booking` as `.existing` (kwarg), with the detail/hint described in Global Constraints.
  Add `BookingRepository.list_active_by_reference(user_id, booking_type, reference_id) -> list[Booking]`
  (owner-scoped, `status != cancelled`, newest first; reuse `_row_to_booking`).
  Add keyword-only `check_duplicate: bool = False` to `BookingService.book_flight` and
  `book_hotel`; when True, after `_replay` and after resolving the flight/hotel (hotel: before
  `is_available`), look up active bookings for that owner + reference and raise on the first
  match per E002 A (flight: `details.passengers == request.passengers`; hotel:
  `details.check_in == request.check_in and details.check_out == request.check_out`). Update
  both docstrings. New tests in `tests/services/test_booking_duplicate.py` — look at
  `tests/services/` + `tests/conftest.py` for the existing DB fixture pattern; name raising cases
  `test_*_raises*` and non-flag cases `test_*_not_flagged*` so SC-1/SC-2 `-k` filters select them;
  use a unique owner id per test so a shared DB cannot leak rows between cases.
- **Verify:** `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/services/test_booking_duplicate.py tests/api/booking -q`
- **Done:** SC-1, SC-2, SC-4 pass; REST routes untouched.
- **Criteria:** SC-1, SC-2, SC-4
- **Interfaces:** Consumes the existing Booking schema and bookings table (pre-existing, no producer task). Produces `DuplicateBookingError` in `apps/api/app/exceptions.py`, `list_active_by_reference` in `apps/api/app/repositories/booking.py`, and the `check_duplicate` kwarg on `BookingService.book_flight` / `book_hotel` in `apps/api/app/services/booking_service.py`.

### Task 2.1 — allow_duplicate override on the agent book tools (wave 2)

- **Files:** apps/api/app/tools/flight_tools.py, apps/api/app/tools/hotel_tools.py, apps/api/tests/tools/test_booking_duplicate_tools.py, apps/api/tests/tools/test_flight_booking_tool.py, apps/api/tests/tools/test_booking_idempotency_tools.py
- **Action:** Add `allow_duplicate: bool = Field(False, description=...)` to `BookFlightArgs` and
  `BookHotelArgs` and the matching tool params (after `confirm`). The description tells the model:
  leave False; if the tool reports a possible duplicate, ask the traveller, and set True only after
  they explicitly confirm they want another booking. Pass `check_duplicate=not allow_duplicate`
  to the service. Keep `allow_duplicate` OUT of the `turn_idempotency_key` args dict (see Global
  Constraints) — add a one-line comment saying why. Add it to `log_tool_call` params. Update
  docstrings (`:param allow_duplicate:`).
  Existing tests that book the identical item twice by design
  (`test_flight_booking_tool.py::test_book_flight_repeated_call_creates_distinct_bookings`,
  `test_booking_idempotency_tools.py::test_book_flight_new_turn_books_again_two_rows` and
  `::test_book_flight_no_context_creates_distinct_bookings`) must pass `allow_duplicate=True` on
  the second call so they keep testing idempotency; do not delete or weaken their asserts. Fix any
  other `tests/tools` case that now trips the check the same way, and list each one in the report.
  New `tests/tools/test_booking_duplicate_tools.py`: new-turn identical flight → ToolException
  containing the first booking's confirmation code and `allow_duplicate`, row count unchanged;
  same with `allow_duplicate=True` → second row; same for hotel; `allow_duplicate` is present in
  the model-facing schema while injected args stay hidden.
- **Verify:** `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/tools -q`
- **Done:** SC-3, SC-5, SC-6 pass.
- **Criteria:** SC-3, SC-5, SC-6
- **Interfaces:** Consumes `check_duplicate` and `DuplicateBookingError` from Task 1.1. Produces the `allow_duplicate` tool argument in `apps/api/app/tools/flight_tools.py` and `apps/api/app/tools/hotel_tools.py`, and `apps/api/tests/tools/test_booking_duplicate_tools.py`.

## 5. Risks

- Shared/session-scoped test DB: an earlier test's active booking for the same owner + flight can trip the check in a later test. Mitigation: unique owner ids in new tests; run the whole `tests/tools` directory in Task 2.1.
- Editing an existing test assert trips the warn-mode `weakening-validation` gate — expected; asserts are kept, only the second call's args change.
- Whether the live model actually asks and retries with `allow_duplicate=True` is prompt-dependent and not covered by the offline suite (recorded under Not auto-verified).
- `flight_tools.py` / `hotel_tools.py` also carry uncommitted gh-191 edits in the main checkout; this branch is off `main`, so a later rebase may conflict there.

## 6. Status Log

- 2026-09-14 — Plan written after intake decisions E001 C / E002 A / E003 A; lane normal.
- 2026-09-14 — task 1.1 complete; commit fd6fe2c; review spec=pass quality=pass. Minor (open, to final chain): M1 hotel dates compared as raw strings — `_valid_date` (schemas/hotel.py:248) keeps non-zero-padded input, so `2027-4-10` vs `2027-04-10` escapes the check; M2 no hotel "cancelled/other owner/flag off" not_flagged cases; M3 hotel raise test does not assert the hint.
- 2026-09-14 — task 2.1 complete; commit 0c79f9e; review spec=pass quality=pass. Minor: M4 no same-turn test for a revise re-run with allow_duplicate flipped (must replay, 1 row); M5 schema test does not assert the allow_duplicate description. Controller re-ran SC-1..SC-6 in the worktree: all exit 0. M1–M5 sent to one fix-up dispatch before the final review chain.
- 2026-09-14 — fix-up M1–M5 complete; commit cc8c32c (hotel dates compared as parsed dates; 5 tests added/tightened). Controller re-ran SC-1..SC-6 @ cc8c32c: all exit 0. Final review chain started on b1b4a73..cc8c32c.
- 2026-09-15 — correctness review: 7 candidates, all scored < 75 (advisory, see SUMMARY). User decided to fix CR-5 anyway (same-turn REVISE flipping allow_duplicate books without confirmation): override honoured only after a HumanMessage follows the duplicate warning; tool layer only. Fix-up dispatched.
- 2026-09-15 — all tasks complete (1.1 fd6fe2c, 2.1 0c79f9e; fix-ups cc8c32c, 4fca57a); correctness + intent review pass (receipt @ 4fca57a); status shipped → PR.
