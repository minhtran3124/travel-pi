# gh-118-trip-ownership — Summary

Lane: high-risk
Confidence: high
Reason: three hard gates fire at once — **authorization** (every trip read/write becomes
user-scoped), **data-loss migration** (the migration empties `trips`, `trip_items` and `expenses`),
and **public contract** (`/trips` and `/expenses` go from unauthenticated to requiring a token).
Confidence is high only because the human narrowed all three scope decisions explicitly before any
code was written; see "Decisions".
Flags: auth, authorization, data-loss/migration, public-contract, high-blast-file
Affects: `app/db/models/trip.py`, a new Alembic revision, `app/repositories/trip.py`,
`app/services/trip_service.py`, `app/routers/trips.py`, `app/routers/expenses.py`,
`app/routers/agent.py`, `app/tools/trip_tools.py`.
Input-type: bug report (GitHub #118)
Route: high-risk → decisions narrowed by the human → implement on a branch off `main`
Escalate: resolved — the three open questions were put to the human and answered before starting.

### Intent

> có (open issues for ownership + trip number) → start implementation now → #118 trip ownership trước

#118: trips have no owner. `trips` has no `user_id`, `TripRepository.list_trips()` returns every
live trip, and a `trip_id` in an `/agent/chat` body is trusted as-is — so any caller who knows or
guesses a UUID reaches that trip's itinerary and expenses. `/trips` has no authentication at all.

### Decisions (human-narrowed, before implementation)

1. **Existing ownerless trips are deleted, not backfilled.** The backfill route named in the issue —
   derive the owner from `conversations.trip_id` — was measured and yields nothing: the dev database
   has **0** conversations with a trip pinned across 35 users. Every one of the 11 trips would have
   stayed ownerless, so the choice was between a permanently-NULL column and a clean start.
   Consequence, stated plainly: **because no trip has an owner yet, "delete ownerless trips" means
   the migration empties the table** — 11 trips, 36 `trip_items`, 10 `expenses` in the dev database.
   `bookings` and `saved_places` are not trip-scoped and are untouched.
2. **`user_id` is `NOT NULL` from the first revision.** Possible only because of (1); it avoids a
   two-step migration and the "NULL means…?" rule that outlives whoever wrote it.
3. **Anonymous callers cannot create trips.** Requiring a login is a breaking change for the
   anonymous agent flow, accepted in exchange for never having an orphan-owner state. The
   alternative (anonymous id + a claim-after-login flow mirroring conversations) was rejected as
   more machinery than the feature is worth right now.
4. **`/trips` and `/expenses` get real authentication in this PR**, rather than scoping only the
   agent path. Scoping one transport and leaving the other open would have closed the hole the
   chatbot uses while leaving the REST hole exactly as wide.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Migration up/down/up | `cd apps/api && alembic upgrade head && alembic downgrade -1 && alembic upgrade head` | 0 | clean on SQLite; `user_id` lands NOT NULL with `ix_trips_user_id`; delete counts logged at WARNING |
| Trip suite | `DATABASE_URL=sqlite:///<tmp> pytest tests/api/trip -q` | 1 | **52 failed, 36 passed — expected and not yet fixed.** See "Status" below. |

### Status — wave 1 of 6 landed, the branch is RED on purpose

`trips.user_id` is `NOT NULL` but nothing writes it yet, so every trip INSERT fails until wave 2
threads an owner through `_new_trip_row` / `create_trip`. 52 trip tests fail for that single reason.

This is a deliberate checkpoint, not a finished state: the schema is the piece every later wave
depends on, and it is verified in isolation. **Do not open a PR from this commit.** The remaining
waves are specified task-by-task in `PLAN.md`:

- **Wave 2** — scope `TripRepository` / `TripService` (this is what makes the suite green again)
- **Wave 3** — require `get_current_user` on `routers/trips.py` and `routers/expenses.py`
- **Wave 4** — validate the agent's `trip_id` against the caller; block anonymous `create_trip`
- **Wave 5** — cross-user negative tests on both transports
- **Wave 6** — correct the "No auth" convention in `CLAUDE.md`

Resume by reading `PLAN.md` from Task 2.1; no context beyond it is needed.

### Rollback

The schema half is reversible; **the data half is not**.

- Revert the code: `git revert <sha>`
- Revert the schema: `cd apps/api && ../../.venv/bin/alembic downgrade -1` — drops `trips.user_id`
  and its index.
- **The deleted trips, trip items and expenses cannot be restored by a downgrade.** `alembic
  downgrade` recreates the column, not the rows. Anyone running this migration against a database
  whose data matters must take a backup first:
  `pg_dump -t trips -t trip_items -t expenses ... > pre-gh118.sql`

This irreversibility was the substance of decision (1) and was accepted knowingly.
