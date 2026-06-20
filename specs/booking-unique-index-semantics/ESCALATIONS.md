# ESCALATIONS — booking-unique-index-semantics

Deny-on-no-response: with no recorded decision, the work stays blocked.

## E1 — #1 confirmation_code uniqueness

**Trigger:** low confidence + data-model hard gate.

**New fact:** `confirmation_code` is NOT independently generated. It is a pure
deterministic function of the booking UUID (`schemas/booking.py: confirmation_code_for`
→ `short_code_for(id)`), stored denormalized only so the index can serve lookups. So a
unique index would convert a rare 6-char hash collision into a **booking-creation
failure** (IntegrityError on insert), not a clean dedupe.

**Options:**
- A. Document best-effort; leave the non-unique index as-is. No schema change.
  Collisions are astronomically rare at mock volume; lookup keeps `.first()`.
- B. Make the index unique AND add collision-retry at ID generation (regenerate the
  UUID when its derived code already exists). Migration + service change.
- C. Widen the derived code (e.g. 7–8 chars) to shrink collision probability without a
  uniqueness constraint. Changes existing codes — breaks any code already in flight.

**Decision:** **B — Unique index + collision-retry.** Make
`ix_bookings_confirmation_code` unique (partial, `WHERE confirmation_code IS NOT NULL`,
mirroring the idempotency index) and make booking-id minting collision-aware:
generate a UUID, derive its code, regenerate if the code already exists.

## E2 — #3 idempotency_key vs soft-delete

**Trigger:** low confidence + data-model hard gate.

**Current behavior:** `get_by_idempotency_key` does not filter `deleted_at`, and the
partial unique index is `WHERE idempotency_key IS NOT NULL`. After a booking is
soft-deleted/cancelled, a re-POST with the same key hits the dead row → returns the
cancelled booking; the key is permanently burned.

**Options:**
- A. Keep current behavior. Idempotency replay returns the existing (even cancelled)
    booking; no new booking is created for a reused key. No change.
- B. Exclude soft-deleted rows from BOTH the partial unique index
    (`... AND deleted_at IS NULL`) and the `get_by_idempotency_key` lookup, so a
    re-POST after cancel creates a fresh booking. Migration + crud change; also decide
    whether the same fix applies to `trips` / `trip_items` (same index pattern).

**Decision:** **A — Keep current (no change).** Idempotency replay returns the
existing booking; reused keys never create a new one. Note: bookings `cancel()` sets
`status='cancelled'`, NOT `deleted_at`, so no booking path actually soft-deletes today —
the "burned key after delete" scenario is not currently reachable for bookings. Closed
as a documented no-op; no migration, no code change.
