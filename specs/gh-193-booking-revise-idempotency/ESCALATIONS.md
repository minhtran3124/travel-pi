<!-- Escalation channel for gh-193-booking-revise-idempotency. DENY-ON-NO-RESPONSE. -->

# gh-193-booking-revise-idempotency — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (correctness-review, finding scored 100 by an independent scorer; reported by the removed-behavior and enclosing-function angles)
- date: 2026-09-11
- trigger: in-flight
- question: How should a booking re-requested in the same turn after a cancel be handled, given that every fix touches `BookingService`/`BookingRepository`, which the REST `Idempotency-Key` path (`routers/flights.py:241`, `routers/hotels.py:307`) shares?
- context: `book_flight(args)` → `cancel_flight` → `book_flight(args)` within one traveller turn now replays the **cancelled** row (`_replay` → `get_by_idempotency_key` filters on key + owner only; `cancel` soft-cancels and keeps the row and its key), so the tool reports `status: cancelled` and no live reservation exists. Before this branch the agent sent no key, so a fresh booking was created. The four task commits are otherwise reviewed clean; this is the only blocking finding.
- options:
  - A) Clear `idempotency_key` when a booking is cancelled (`BookingRepository.update_status` / `BookingService.cancel`, one line + test). A cancelled booking stops being a replay target for both the agent and REST, so the re-book creates a fresh row. Consequence: a REST client that retries its original POST after cancelling gets a new booking instead of the cancelled one — a behaviour change, arguably the correct one. Smallest, deterministic. (Recommended.)
  - B) Make `_replay` ignore rows with `status == cancelled`. Alone this is insufficient: the fresh insert collides with the cancelled row on the unique `ix_bookings_idempotency_key` index and `repo.add` returns the cancelled winner — so B needs A's key clearing anyway.
  - C) Leave the service untouched and record the finding as a known limitation of the turn-scoped key (book→cancel→re-book with identical args in one turn). Ships the branch as is; the double-booking fix stays intact; the rare sequence regresses versus main.
- default_if_no_response: BLOCK
- decision: A — clear `idempotency_key` when a booking is cancelled, so a cancelled row is never a replay target (agent and REST alike); add a test for book → cancel → re-book creating a fresh row.
- decided_by: Minh Tran (user, via AskUserQuestion)
- decided_at: 2026-09-11
