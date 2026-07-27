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
| Migration up/down/up | `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` | 0 | clean on SQLite; `user_id` lands NOT NULL with `ix_trips_user_id`; delete counts logged at WARNING |
| Cross-user access | `pytest tests/api/trip/test_trip_ownership.py -q` | 0 | 13 passed — the negative cases are the point: B cannot list, read, update, delete, add items to, budget or detail A's trip, cannot attach an expense to it, and a rejected DELETE does not silently perform the write |
| Full backend suite | `DATABASE_URL=sqlite:///<tmp> pytest tests/ -q` | 1 | 1811 passed, 5 failed — the **same 5** pre-existing `.env` leaks that fail identically on unmodified `main` |
| Lint | `ruff check app scripts` | 0 | clean |
| Format | `ruff format` on every changed `.py` | 0 | 6 files reformatted, then clean |

### What changed, by wave

1. **Schema** — `trips.user_id` NOT NULL + index; the migration empties `expenses`, `trip_items`,
   `trip_place_link` and `trips`, and clears `conversations.trip_id`.
2. **Data access** — the owner is bound to the `TripService` *instance*, not threaded through twenty
   method signatures. Every read and mutation already funnelled through `get_trip()`, so scoping
   that one lookup scoped the whole surface and no future method can forget to pass it. A trip owned
   by someone else raises the same `NotFoundError` as one that does not exist — a distinct
   "forbidden" would confirm to a probe that a guessed id is real. `get_trip_by_idempotency_key` is
   scoped too, or a replay could hand one user another's trip on a key collision.
3. **Routes** — `get_trip_service` and `get_expense_service` now depend on `get_current_user` (the
   *required* variant), so every route on both routers 401s without a token. They had no
   authentication at all before.
4. **Agent** — the five `InjectedState("trip_id")` tools gained an injected `user_id` and construct
   the scoped service; `load_context` loads the trip snapshot through it, so a foreign `trip_id` in
   state yields nothing instead of leaking a title and city into the system prompt. `create_trip`
   refuses an anonymous caller via a new `AgentContext.authenticated` flag, which defaults **False**
   so any path that forgets to resolve identity is treated as anonymous rather than silently
   granted.
5. **Tests** — 13 cross-user cases; the shared `client` fixture authenticates as a fixed traveller,
   and the four agent tests that open a trip now sign in.
6. **Docs** — `CLAUDE.md` claimed "No auth, pagination, or rate limiting", which was already partly
   false and is now clearly false; corrected rather than left contradicting the code.

### Deviations

- **Rule 2 (auto-add)** — `AgentContext.authenticated` was not in the plan. Blocking anonymous trip
  creation needs to distinguish "anonymous id" from "authenticated id", and the agent path had no
  such signal: `_effective_user_id` returns a client-supplied string for anonymous callers, which is
  indistinguishable from a real subject downstream.
- **Plan task 4.1, partially reinterpreted.** The plan said to reject a foreign `trip_id` at the
  router. It is instead denied at the data layer — every consumer of `state["trip_id"]` is
  owner-scoped, so a foreign id yields nothing anywhere. A router-side pre-check would add a DB
  round-trip per request to convert silent emptiness into an explicit error; worth doing, not worth
  blocking this on. Recorded rather than silently dropped.

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
