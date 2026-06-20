# booking-unique-index-semantics — Summary

Lane: high-risk
Confidence: low
Reason: Both items alter uniqueness constraints on `bookings` (schema/migration hard gate) and change existing booking-lookup / idempotency-replay behavior; resolution requires a design decision per item.
Flags: data-model, existing-behavior, public-contract
Affects: bookings table (`ix_bookings_confirmation_code`, `ix_bookings_idempotency_key`); booking lookup + idempotency-replay contract
Input-type: change request

> `Lane` drives ceremony; `Confidence` drives interruption. A migration/uniqueness
> change is a hard gate → high-risk. Low confidence (ambiguous direction on both
> items) escalates before any code — see ESCALATIONS.md.

### Intent

From the prior DB-design review, the user selected two findings to act on:

**#1 (confirmation_code lookup key is not unique):**
"`booking_service` treats it as an alternate primary lookup (`get_by_confirmation_code` → `.first()`), but `ix_bookings_confirmation_code` is a non-unique index. It's a 6-char generated code, so collisions are possible, and `.first()` would silently return the wrong booking. Either make the index unique (and handle collision at generation), or document that it's best-effort."

**#3 (soft-deleted rows still hold the idempotency_key):**
"The partial unique index is `WHERE idempotency_key IS NOT NULL` — it does not exclude `deleted_at IS NOT NULL`. So once a booking/trip is soft-deleted, its idempotency_key is permanently burned; a later request with the same key collides with a dead row instead of creating fresh. If retries-after-cancel should succeed, the partial predicate needs `AND deleted_at IS NULL`."

User request verbatim: "/feature-intake for #1 and #3"

## What changed

**#1 implemented.** `ix_bookings_confirmation_code` is now a UNIQUE partial index
(`WHERE confirmation_code IS NOT NULL`, mirroring the idempotency index), and
`BookingService._mint_booking_id()` mints a UUID whose derived 6-char code is unused
(bounded retry, `_MAX_ID_ATTEMPTS=8`) so the unique constraint never surfaces as an
insert failure. Both `book_flight` / `book_hotel` call it. New Alembic migration
`c3e5a7b9d1f2` (chains onto squashed head `7b300c56abff`) drops + recreates the index as
unique; reversible. Two tests added (collision-retry; DB-level duplicate rejection).

**#3 closed as a no-op** — decision E2 = keep current. The settled model
(`TimestampMixin`) has no `deleted_at` column at all, so the "burned key after
soft-delete" scenario is structurally unreachable for bookings.

Files touched: `app/db/models/booking.py`, `app/services/booking_service.py`,
`alembic/versions/c3e5a7b9d1f2_bookings_confirmation_code_unique.py`,
`tests/api/booking/test_bookings.py`.

### Verify
| Check | Command | Exit | Notes |
|---|---|---|---|
| Lint | `ruff check app scripts tests/api/booking/test_bookings.py` | 0 | All checks passed |
| Migration fresh apply | `alembic upgrade head` (fresh sqlite) | 0 | 7b300c56abff → c3e5a7b9d1f2 |
| Migration reversible | `alembic downgrade -1` then `upgrade head` | 0 | index unique→non-unique→unique |
| Unique index present | `pragma_index_list('bookings')` | 0 | ix_bookings_confirmation_code unique=1 |
| Booking suite (SQLite) | `pytest tests/api/booking/test_bookings.py` | 0 | 40 passed (38 + 2 new) |
| Full suite (SQLite) | `make test` | 0 | 667 passed |
| Cross-engine parity (Postgres) | `make test-docker` | 0 | 667 passed |

### Rollback
- Revert migration: `alembic downgrade 7b300c56abff`
- Revert code: `git revert <sha>` (model + service + tests in one commit)

### Rationale

Classified high-risk because each item mutates a uniqueness constraint on `bookings`
(an Alembic migration + a change to client-visible lookup/idempotency behavior).
Confidence is low because each item, as I raised it, was framed as a decision
("make unique vs document", "confirm intent") with ≥2 materially different outcomes —
and a new fact (the confirmation code is a deterministic function of the UUID, not an
independent value) makes the naive "add a unique index" path actively harmful.

### Alternatives considered

Per-item options are enumerated in ESCALATIONS.md.

## Status

Shipped pending commit. #1 implemented + verified on both engines; #3 closed as no-op.
