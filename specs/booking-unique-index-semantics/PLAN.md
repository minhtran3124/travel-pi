---
slug: booking-unique-index-semantics
status: shipped
owner: Minh Tran
created: 2026-06-19
---

# Booking confirmation_code uniqueness (#1)

## 1. Motivation

`booking_service.get()` treats the derived 6-char `confirmation_code` as an
alternate lookup key (`get_by_confirmation_code` → `.first()`), but
`ix_bookings_confirmation_code` is non-unique, so a hash collision would make the
lookup silently return the wrong booking. The code is a deterministic function of
the booking UUID (`short_code_for(id)`, 31⁶ ≈ 887M space), so the fix is: enforce a
unique index AND make id-minting collision-aware (regenerate the UUID if its derived
code already exists). Decision E1 = option B (see SUMMARY/ESCALATIONS).

#3 (idempotency_key vs soft-delete) is closed as a no-op — decision E2 = keep current.

## 2. Non-goals

- No change to the `short_code_for` algorithm or code length (would break existing codes).
- No change to hotels/places short codes (HTL-/place codes stay non-unique, derived display-only).
- No idempotency_key / soft-delete change (#3 closed).

## 3. Success Criteria

- `ix_bookings_confirmation_code` is unique (partial: `WHERE confirmation_code IS NOT NULL`).
- A second booking whose UUID derives a colliding code never reaches the DB — id-minting retries.
- Full suite green on SQLite and Postgres; migration applies + downgrades clean.

## 4. Tasks

### Task 1.1 — Unique index + collision-aware id minting + migration

```xml
<task id="1.1" wave="1">
  <files>app/db/models/booking.py, app/services/booking_service.py, alembic/versions/0005_bookings_confirmation_code_unique.py</files>
  <action>1) booking.py: make ix_bookings_confirmation_code unique with partial predicate (sqlite_where/postgresql_where = "confirmation_code IS NOT NULL"), mirroring ix_bookings_idempotency_key. 2) booking_service.py: replace module-level _new_booking_id() with a BookingService method that loops (bounded, e.g. 8 attempts): mint str(uuid4), derive confirmation_code_for(id), accept if self._repo.get_by_confirmation_code(code) is None, else retry; raise RuntimeError if exhausted. Update both call sites (book_flight, book_hotel) to self._new_booking_id(). Import confirmation_code_for from app.schemas.booking. 3) New migration 0005 chaining onto head 4d12b875ef3f: batch_alter_table('bookings') drop ix_bookings_confirmation_code, recreate unique with partial predicate; downgrade reverses to non-unique.</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi && .venv/bin/alembic upgrade head && .venv/bin/python -m pytest tests/api/booking/test_bookings.py -q</verify>
  <done>Migration applies; booking API tests pass; index is unique in schema.</done>
</task>
```

### Task 1.2 — Collision + uniqueness tests

```xml
<task id="1.2" wave="2">
  <files>tests/api/booking/test_bookings.py</files>
  <action>Add: (a) test that _new_booking_id retries past a forced collision — monkeypatch uuid.uuid4 to yield a colliding id (one whose code already exists) then a fresh one, assert the returned id derives an unused code; (b) test that the DB rejects a directly-inserted duplicate confirmation_code (IntegrityError) to prove the unique index. Keep existing assertions intact.</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi && .venv/bin/python -m pytest tests/api/booking/test_bookings.py -q</verify>
  <done>New tests pass; whole booking suite green.</done>
</task>
```

## 5. Risks

- Migration on a unique index fails if existing data already holds a duplicate code — acceptable at mock volume (fresh/regenerable booking data); note in SUMMARY.
- The retry loop adds one extra read per booking create — negligible (indexed lookup).

## 6. Status Log

- 2026-06-19 — intake high-risk/low-confidence → escalated → decisions E1=B, E2=A. Plan active.
- 2026-06-19 — paused: branch `refactor/models-uuid-timestamp-base` was mid-restructure
  (models flipped base, migrations squashed). Captured findings to RESEARCH.md.
- 2026-06-20 — branch settled on `v3` (uuid mixins, single migration `7b300c56abff`,
  non-unique index intact). Resumed + shipped #1: model unique index, `_mint_booking_id`
  collision-retry, migration `c3e5a7b9d1f2`, 2 tests. `make test` + `make test-docker`
  both 667 passed. #3 closed (no `deleted_at` column exists → unreachable).
