# gh-118 — Give trips an owner and scope every path to it

**Base:** `github/main` (`6165903`). **Branch:** `feat/gh-118-trip-ownership`.
Decisions are recorded in `SUMMARY.md` and were narrowed by the human before implementation.

Ordering matters: the schema lands first because every later wave depends on the column existing,
and the routes are hardened before the agent path so the agent's validation has something to lean on.

---

### Task 1.1 — Owner column and the migration that empties the table (wave 1)

- **Files:** apps/api/app/db/models/trip.py, apps/api/alembic/versions/<new>_trip_user_id.py
- **Action:** Add `user_id: Mapped[str]` (`String`, `nullable=False`, indexed) to `Trip`. Write the
  revision: delete `expenses` and `trip_items` rows first (they reference a trip), then every row in
  `trips`, then add the column `NOT NULL` with its index. Deleting before adding is what makes
  `NOT NULL` possible in one step — no trip has an owner today, so every row is ownerless by
  definition. Also `NULL` out `conversations.trip_id` so no conversation points at a deleted trip
  (0 rows today, but the migration must not depend on that staying true). Log the deleted counts.
  `downgrade()` drops the column and index and **cannot restore the rows** — say so in its docstring.
- **Verify:** `cd apps/api && ../../.venv/bin/alembic upgrade head && ../../.venv/bin/alembic downgrade -1 && ../../.venv/bin/alembic upgrade head`
- **Done:** `trips.user_id` exists, is `NOT NULL` and indexed; upgrade→downgrade→upgrade is clean.

### Task 2.1 — Scope the repository and service (wave 2)

- **Files:** apps/api/app/repositories/trip.py, apps/api/app/services/trip_service.py
- **Action:** Thread the owner through data access: `list_trips(user_id)` filters by it;
  `get_trip(trip_id, user_id)` returns None for a trip the caller does not own (**not** a different
  error — a "forbidden" that differs from "not found" tells an attacker the id was real);
  `create_trip` stamps it. Same for `update_trip`, `delete_trip`, budget caps and trip places, which
  all reach a trip by id.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/trip -q`
- **Done:** no repository method reaches a trip without an owner argument.

### Task 3.1 — Require auth on the trip and expense routes (wave 3)

- **Files:** apps/api/app/routers/trips.py, apps/api/app/routers/expenses.py
- **Action:** Add `get_current_user` (the required variant, `app/core/auth.py:115`) as a dependency
  and pass its id into the service. These routers have no authentication at all today. Expenses are
  reached through their trip, so scoping the trip is what scopes them — verify each expense route
  resolves its trip through the scoped lookup rather than by raw `trip_id`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/trip tests/api/expense -q`
- **Done:** every route on both routers 401s without a token and only ever returns the caller's data.

### Task 4.1 — Scope the agent path (wave 4)

- **Files:** apps/api/app/routers/agent.py, apps/api/app/tools/trip_tools.py
- **Action:** A `trip_id` in the request body is currently trusted verbatim — validate it belongs to
  the resolved user and reject it otherwise, rather than passing it into graph state. `create_trip`
  (the tool) stamps the resolved owner and refuses when the caller is anonymous, per decision (3).
  The refusal must read as "sign in to save a trip", not as a tool failure.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent tests/agents -q`
- **Done:** an agent request carrying someone else's `trip_id` cannot read that trip; an anonymous
  caller cannot create one.

### Task 5.1 — Cross-user tests (wave 5)

- **Files:** apps/api/tests/api/trip/test_trip_ownership.py, apps/api/tests/api/agent/test_agent_trip_scope.py
- **Action:** The tests that matter are the negative ones: user B cannot read, update, delete or add
  places to user A's trip through REST; user B cannot reach it through `/agent/chat` by supplying the
  id; an unauthenticated request 401s; an anonymous agent caller cannot create a trip. Assert on
  status codes and on the absence of A's data in B's responses.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///$(mktemp -d)/t.db ../../.venv/bin/python -m pytest tests/ -q`
- **Done:** every negative case is covered and the full suite is green apart from the 5 known
  `.env`-leak failures.

### Task 6.1 — Reconcile the docs (wave 6)

- **Files:** CLAUDE.md, WORKFLOW.md
- **Action:** `CLAUDE.md` states "No auth, pagination, or rate limiting" as a project convention.
  That is now false for trips and expenses (and was already partly false — the agent has Supabase
  auth and rate limiting exists). Correct it rather than leaving a convention that contradicts the
  code.
- **Verify:** `grep -n "No auth" CLAUDE.md`
- **Done:** the stated convention matches the code.

---

## Out of scope

- **The trip number (#119).** Unblocked by this work, implemented separately.
- **Ownership for `bookings` and `saved_places`.** Neither is trip-scoped; they have their own
  (missing) ownership story, which is not this issue.
- **Restoring the deleted trips.** Not possible; see `SUMMARY.md` → Rollback.
