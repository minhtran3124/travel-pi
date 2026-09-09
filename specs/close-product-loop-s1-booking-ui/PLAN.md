---
slug: close-product-loop-s1-booking-ui
status: shipped
owner: Minh Tran
created: 2026-09-08
---

# Flights & hotels UI, premium gate, booking ↔ trip

## 1. Motivation

A third of the agent's tools have no screen, and no user can book from the web at all: flight and
hotel booking exist only inside the chat, and only for premium accounts, because the supervisor is
the only thing that checks tier. This slice gives searching and booking their own pages, moves the
premium check onto the REST routes that those pages call, and links a booking to a trip so the
trip's Bookings tab and Budget tab can show it.

Approved design: `specs/close-product-loop/design.md` §5 S1 (approved 2026-09-08, amended the same
day after research). Research: `specs/close-product-loop-s1-booking-ui/research-brief.md`.

## 2. Non-goals

- No real inventory, provider, or payment. Flights and hotels stay hash-seeded.
- No change to the agent path. Tools call `BookingService` directly and stay gated by the
  supervisor; this plan does not move that gate.
- No change to `_spend_by_category` or `total_spent`. `booked_total` is added beside them.
- No `code` field on the error envelope. The exception class name is the discriminator.
- No new agent tool, no MCP surface change (booking tools are already excluded).
- No S2–S6 work (guide pages, map, Today, .ics, recap, share link).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | A free user's POST to a book route is refused with 403 and the `PremiumRequiredError` discriminator | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_premium_gate.py -q` | exit 0 |
| SC-2 | A premium user's POST to a book route still succeeds and the agent's booking path is unchanged | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_premium_gate.py tests/api/agent/test_quota.py -q` | exit 0 |
| SC-3 | The `bookings.trip_id` migration applies and reverses on an empty database | `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_bookings_trip_id_migration.py -q` | exit 0 |
| SC-4 | Booking with a `trip_id` the caller does not own is refused with 404, and booking without one still works | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_booking_trip_link.py -q` | exit 0 |
| SC-5 | `GET /bookings?trip_id=` returns only that trip's bookings for that owner | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_booking_list_trip_filter.py -q` | exit 0 |
| SC-6 | `TripBudget.booked_total` counts each non-cancelled booking on the trip once and leaves `total_spent` unchanged | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/trip/test_trip_budget_booked_total.py -q` | exit 0 |
| SC-7 | The eight existing chat-panel tests still pass after the result cards are extracted | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/chat/panel/FlightsPanel.test.tsx src/components/chat/panel/HotelsPanel.test.tsx` | exit 0 |
| SC-8 | A 403 from a book call raises `PremiumRequiredError` in the FE, distinct from a 404 | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/lib/api/errors.test.ts src/lib/query/booking-mutations.test.tsx` | exit 0 |
| SC-9 | `/flights` and `/hotels` render a search form, list results, and open a book dialog | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/app/flights/page.test.tsx src/app/hotels/page.test.tsx` | exit 0 |
| SC-10 | The trip Bookings tab lists that trip's bookings and the Budget tab shows both totals | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/bookings/BookingsTab.test.tsx src/components/trips/budget/BudgetTab.test.tsx` | exit 0 |
| SC-11 | Every new UI string exists in both locales | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/messages.parity.test.ts` | exit 0 |
| SC-12 | The frontend typechecks against the regenerated OpenAPI types | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec tsc --noEmit` | exit 0 |
| SC-13 | Backend lint is clean after the change | `cd apps/api && ../../.venv/bin/ruff check app` | exit 0 |
| SC-14 | The booking end-to-end spec is collectable by Playwright | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec playwright test --list playwright/booking-smoke.spec.ts` | exit 0 |

## Global Constraints

- **Branch isolation.** All work happens on `feat/close-product-loop-s1-booking-ui`, created off
  `main` via `using-git-worktrees`. Never commit to `main`.
- **Error style.** Raise domain exceptions from `app/exceptions.py`, never `HTTPException`. Do not
  add a `code` field to the error envelope; the envelope's existing `error` field carries the
  exception class name.
- **Tier is server-resolved.** Read it through `UserRepository.get_tier`, never from a request
  body or header. `get_tier` returns a plain `str`; coerce with `Tier(...)` and fall back to
  `Tier.FREE` on an unknown value, as `app/agents/context.py:82` does.
- **Money comes from inventory.** `total_price` and `currency` are taken from the resolved flight
  or hotel row, never from the client.
- **Migrations.** One new Alembic revision chaining off the current single head `a7c3e9f1b2d4`.
  Every column add goes inside `op.batch_alter_table`, with the mirror drop in `downgrade`.
  `bookings.trip_id` is a plain indexed `String`, nullable, with no foreign key, matching
  `trip_items.trip_id` (`app/db/models/trip.py:48`).
- **Do not change existing budget maths.** `_spend_by_category` and `total_spent` stay as they are.
- **Do not change the agent path.** No edits under `app/agents/`, `app/tools/`, or `app/mcp/`.
- **Frontend conventions.** Client components; TanStack Query hooks in `src/lib/query/` with keys
  from `src/lib/api/keys.ts`; one `useState` per form field, no form library; `Modal` from
  `src/components/ui/`; never `max-w-md` (the spacing scale shadows the container scale) — use
  `max-w-[28rem]`.
- **i18n.** Every new string goes into `messages/en.json` and `messages/vi.json` in the same edit.
  Never call `t.has`.
- **Tests.** MSW handlers per test (`server.use`), never a global fetch mock; the setup file runs
  with `onUnhandledRequest: "error"`, so every request a test triggers needs a handler.
- **Editing hazard.** The ruff-on-edit hook deletes an import added before its first use; add the
  import and its usage in the same edit.
- **Node.** Prefix every `pnpm` command with the Node 24 PATH shown in the checks above.
- **Never run the whole suite in a task Verify.** The full run happens at
  `finishing-a-development-branch`.

## 4. Tasks

### Task 1.1 — Premium gate on the two book routes (wave 1)

- **Files:** apps/api/app/exceptions.py, apps/api/app/core/auth.py, apps/api/app/routers/flights.py, apps/api/app/routers/hotels.py, apps/api/tests/api/booking/test_premium_gate.py
- **Action:** Write `tests/api/booking/test_premium_gate.py` first: a caller with no `users` row
  (tier resolves to `free`) POSTing `/flights/book` and `/hotels/book` gets 403 with body
  `error == "PremiumRequiredError"`; a caller whose tier was set with
  `UserRepository(s).upsert_tier(uid, "premium")` gets a created booking. Follow the fixture shape
  in `tests/api/agent/test_quota.py:52-56`.
  Then add `PremiumRequiredError(ForbiddenError)` to `app/exceptions.py`, and a `require_premium`
  dependency to `app/core/auth.py` modelled on the nested-dependency factory in
  `app/core/rate_limit.py:143-165` — it takes the request-scoped session and `CurrentUserDep`,
  reads the tier via `UserRepository`, and raises `PremiumRequiredError` with a `hint` naming the
  upgrade path. Attach it to `POST /flights/book` and `POST /hotels/book` and add `403` to each
  route's `error_responses(...)` list. Do not touch any other route.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_premium_gate.py -q`
- **Done:** Free callers are refused with 403 and the `PremiumRequiredError` discriminator on both
  book routes; premium callers still receive a booking; no other route gained a tier check.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes the existing tier lookup, tier enum, and forbidden-error base already in the codebase. Produces `require_premium` in `apps/api/app/core/auth.py` and `PremiumRequiredError` in `apps/api/app/exceptions.py`.

### Task 1.2 — `bookings.trip_id` column, migration, and repository mapping (wave 1)

- **Files:** apps/api/alembic/versions/b8e4c1f7a305_add_bookings_trip_id.py, apps/api/app/db/models/booking.py, apps/api/app/repositories/booking.py, apps/api/tests/db/test_bookings_trip_id_migration.py
- **Action:** Write `tests/db/test_bookings_trip_id_migration.py` first, following the round-trip
  template in `tests/db/test_content_translations_migration.py:44-60`: upgrade to the previous
  revision, assert the column and index are absent, upgrade to head, assert both exist, downgrade,
  assert both are gone.
  Then add the Alembic revision chaining off head `a7c3e9f1b2d4`, with a module docstring stating
  it is additive. Inside one `op.batch_alter_table("bookings")`, add
  `sa.Column("trip_id", sa.String(), nullable=True)` and `create_index("ix_bookings_trip_id",
  ["trip_id"], unique=False)`; mirror both in `downgrade`. Add the matching
  `trip_id: Mapped[str | None]` to the ORM model, and teach `_row_to_booking`
  (`app/repositories/booking.py:17-33`) and `add` (`:163-186`) to carry the field. Do not add a
  foreign key.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_bookings_trip_id_migration.py -q`
- **Done:** The revision applies and reverses on an empty database; the ORM row and both repository
  mappings carry `trip_id`; `alembic heads` still reports exactly one head.
- **Criteria:** SC-3
- **Interfaces:** Consumes the current Alembic head a7c3e9f1b2d4. Produces `apps/api/alembic/versions/b8e4c1f7a305_add_bookings_trip_id.py` and a `trip_id` field on the `bookings` row.

### Task 1.3 — Restore the suite the premium gate regressed (wave 1b)

- **Files:** apps/api/tests/conftest.py, apps/api/app/core/auth.py, apps/api/tests/api/booking/test_booking_ownership.py
- **Action:** The shared `client` fixture authenticates as `DEFAULT_TEST_USER_ID`, for whom no
  `users` row exists, so the tier resolves to `free` and every pre-existing test that POSTs a book
  route now gets 403. Seed that caller as premium immediately after `seed_all(...)` in the shared
  fixture, using `UserRepository(session).upsert_tier(DEFAULT_TEST_USER_ID, "premium")`, so the
  shared suite exercises the real dependency as an entitled caller. Do not override
  `require_premium`; the gate must stay live. The dedicated gate tests in
  `tests/api/booking/test_premium_gate.py` build their own app and are unaffected.
  Also delete the unused `RequirePremiumDep` alias from `app/core/auth.py`; both routers use
  `Depends(require_premium)` inline and nothing references the alias.
  `tests/api/booking/test_booking_ownership.py` builds its own owner-a / intruder-b clients and
  books a flight during fixture setup, so the shared seeding does not reach it; seed premium for
  those users in that file's own fixture too, leaving its ownership assertions untouched.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api tests/infra -q`
- **Done:** No test in `tests/api` or `tests/infra` fails with `PremiumRequiredError` as its
  cause, `pytest tests/api/booking` exits 0, and `tests/api/booking/test_premium_gate.py` still
  passes its free-caller 403 cases. The dashboard basic-auth 401s in `tests/api/routes` and
  `tests/api/prompts` are a pre-existing environment failure (the guard reads `apps/api/.env`),
  are unrelated to this branch, and are out of scope for this task.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes the gate from Task 1.1. Produces a premium-seeded shared fixture in `apps/api/tests/conftest.py`.

### Task 2.1 — Optional `trip_id` on both book requests, owner-verified (wave 2)

- **Files:** apps/api/app/schemas/flight.py, apps/api/app/schemas/hotel.py, apps/api/app/schemas/booking.py, apps/api/app/services/booking_service.py, apps/api/tests/api/booking/test_booking_trip_link.py
- **Action:** Write `tests/api/booking/test_booking_trip_link.py` first: booking with a `trip_id`
  the caller owns returns a booking whose `trip_id` matches; booking with another user's `trip_id`
  returns 404; booking with no `trip_id` still succeeds with `trip_id` null; an idempotent replay
  returns the original booking unchanged even when the second request carries a different
  `trip_id`.
  Then add `trip_id: str | None = None` to `FlightBookingRequest` and `HotelBookingRequest`, and
  expose `trip_id` on the `Booking` response schema. In `BookingService.book_flight` and
  `book_hotel`, after the `_replay` check and before constructing the booking, verify an incoming
  `trip_id` belongs to the caller and raise `NotFoundError` when it does not. Keep `total_price`
  and `currency` sourced from the resolved inventory row.
  Include a repository round-trip assertion: a booking written with a `trip_id` reads back with
  the same `trip_id`. Task 1.2 wired both repository mappings, but the field could not survive a
  round trip until this task adds it to the `Booking` schema, so 1.2's mapping is unproven until
  this test exists. Once the field exists, read it as a plain attribute rather than through a
  defensive `getattr`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_booking_trip_link.py -q`
- **Done:** A booking can be attached to a trip the caller owns, another user's trip is rejected
  with 404, the field stays optional, and replay semantics are unchanged.
- **Criteria:** SC-4
- **Interfaces:** Consumes the `trip_id` column from Task 1.2 and the existing trip-ownership check. Produces `trip_id` on `apps/api/app/schemas/booking.py` and on both book request schemas.

### Task 3.1 — `GET /bookings?trip_id=` filter (wave 3)

- **Files:** apps/api/app/routers/bookings.py, apps/api/app/services/booking_service.py, apps/api/tests/api/booking/test_booking_list_trip_filter.py
- **Action:** Write `tests/api/booking/test_booking_list_trip_filter.py` first: with two bookings on
  trip A, one on trip B, and one unlinked, `GET /bookings?trip_id=A` returns exactly the two;
  omitting the parameter returns all four; another user's booking on trip A never appears.
  Then add an optional `trip_id` query parameter to `list_bookings` and extend
  `_filter_and_sort` (`app/services/booking_service.py:57-95`) to filter on it in Python, matching
  how `q` and `type` are already handled. Do not add a repository query. Leave a one-line comment
  saying the filter is in Python because it mirrors `q` and `type`, not because the scale demands
  it.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking -q -p no:randomly`
- **Done:** The filter returns only the named trip's bookings for the calling owner, omitting it
  preserves today's response, and every other test in `tests/api/booking` still passes.
  The Verify runs the whole directory on purpose: `tmp_db` is session-scoped, so a new test file
  sharing a hard-coded booking id with an existing one collides on the derived
  `confirmation_code`, which a file-scoped run cannot see.
- **Criteria:** SC-5
- **Interfaces:** Consumes `trip_id` on the booking read model. Produces a `trip_id` query parameter on `GET /bookings` in `apps/api/app/routers/bookings.py`.

### Task 3.2 — `TripBudget.booked_total` (wave 3)

- **Files:** apps/api/app/schemas/trip.py, apps/api/app/services/trip_service.py, apps/api/tests/api/trip/test_trip_budget_booked_total.py
- **Action:** Write `tests/api/trip/test_trip_budget_booked_total.py` first, pinning the intended
  divergence from `total_spent`: a booking carrying the trip's `trip_id` but referenced by no
  itinerary item raises `booked_total` and leaves `total_spent` at zero; a booking referenced by
  two itinerary items counts once in `booked_total` and twice in `total_spent`; a cancelled
  booking counts in neither.
  Then add `booked_total: float` to `TripBudget` and compute it in `TripService._build_budget`
  (`app/services/trip_service.py:443-470`) from the caller's non-cancelled bookings carrying this
  `trip_id`. Do not modify `_spend_by_category` or `total_spent`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/trip -q -p no:randomly`
- **Done:** `booked_total` counts each non-cancelled booking on the trip once; `total_spent` and the
  per-category rollup return the same values they did before this task; every other test in
  `tests/api/trip` still passes.
- **Criteria:** SC-6
- **Interfaces:** Consumes bookings filtered by `trip_id`. Produces `booked_total` on `apps/api/app/schemas/trip.py`.

### Task 4.1 — Extract the flight and hotel result cards (wave 4)

- **Files:** apps/web/src/components/flights/FlightResultCard.tsx, apps/web/src/components/hotels/HotelResultCard.tsx, apps/web/src/components/chat/panel/FlightsPanel.tsx, apps/web/src/components/chat/panel/HotelsPanel.tsx
- **Action:** Move the per-row renderer out of each panel into its own component, and have the panel
  import it. Preserve exactly, or the existing panel tests fail: the `{f, cheapest}` and
  `{h, cheapest}` prop shapes; the `Panel` translation namespace; the UTC pinning of `hhmm()` via
  `toUtcDate`; the `ring-2 ring-lime` marker on the cheapest row; the `alt` text on the hotel
  thumbnail; and the collapsed-until-clicked split that hides `seats left`, `842 reviews`, and the
  description. Do not change the panels' own props, the panel registry, or `PanelIntlProvider`.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/chat/panel/FlightsPanel.test.tsx src/components/chat/panel/HotelsPanel.test.tsx`
- **Done:** Both cards live in their own files and are imported by the panels; all eight existing
  panel tests pass unchanged.
- **Criteria:** SC-7
- **Interfaces:** Consumes the existing flight and hotel panel row types. Produces `apps/web/src/components/flights/FlightResultCard.tsx` and `apps/web/src/components/hotels/HotelResultCard.tsx`.

### Task 4.2 — Frontend data layer: 403 error type, idempotency, search and book hooks (wave 4)

- **Files:** apps/web/src/lib/api/errors.ts, apps/web/src/lib/api/client.ts, apps/web/src/lib/api/keys.ts, apps/web/src/lib/api/schema.d.ts, apps/web/src/lib/query/flights.ts, apps/web/src/lib/query/hotels.ts, apps/web/src/lib/api/errors.test.ts, apps/web/src/lib/query/booking-mutations.test.tsx
- **Action:** Write `src/lib/api/errors.test.ts` and `src/lib/query/booking-mutations.test.tsx`
  first, using MSW handlers that return 403 and 404 for the book paths, and assert that only the
  403 produces a `PremiumRequiredError`.
  Then in `errors.ts`, lift the hint-carrying constructor into a shared base class, keep
  `ConflictError` extending it so the three existing call sites and their `instanceof` checks are
  untouched, add `PremiumRequiredError` alongside it, and add `throwOn403` mirroring `throwOn409`.
  Add `/flights/book` and `/hotels/book` to `IDEMPOTENT_POST_PATHS` in `client.ts`. Add query-key
  factories and the search plus book hooks for both domains, reading `response` and calling
  `throwOn403` before the generic `throw error`, as `useCreateSavedPlace` does. Regenerate
  `schema.d.ts` with `pnpm gen:api`; this reads `http://localhost:8000/openapi.json`, so start the
  API first (`make api`, or `docker compose up -d` from `apps/api`) or the regeneration writes
  nothing and the typecheck fails for an unrelated reason.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/lib/api/errors.test.ts src/lib/query/booking-mutations.test.tsx`
- **Done:** A 403 book response raises `PremiumRequiredError` and a 404 does not; both book paths
  send an `Idempotency-Key`; the three existing `throwOn409` call sites are unchanged.
  The project-wide typecheck over the regenerated `schema.d.ts` is Task 7.1's gate, not this
  task's: a whole-project `tsc` here would read Task 4.1's files while that sibling is still
  mid-edit in the same wave.
- **Criteria:** SC-8
- **Interfaces:** Consumes the 403 contract from Task 1.1 and the `trip_id` field from Task 2.1. Produces `PremiumRequiredError` and `throwOn403` in `apps/web/src/lib/api/errors.ts`, plus `apps/web/src/lib/query/flights.ts` and `apps/web/src/lib/query/hotels.ts`.

### Task 5.1 — `/flights` and `/hotels` pages, upgrade dialog, nav (wave 5)

- **Files:** apps/web/src/app/flights/page.tsx, apps/web/src/app/hotels/page.tsx, apps/web/src/components/booking/UpgradeDialog.tsx, apps/web/src/components/app-shell/AppShell.tsx, apps/web/messages/en.json, apps/web/messages/vi.json, apps/web/src/app/flights/page.test.tsx, apps/web/src/app/hotels/page.test.tsx
- **Action:** Build both pages as client components following the state ladder in
  `src/app/bookings/page.tsx:132-151` — spinner, error empty state, empty result state, then the
  list. `/flights` collects origin, destination, departure date, optional return date and
  passengers; `/hotels` collects city, check-in, check-out, rooms, adults and children and reads
  availability. Render results with the cards from Task 4.1. A Book action opens a `Modal`
  collecting the traveller name, phone, and an optional trip selection, pre-filled from a
  `?tripId=` query parameter when present; on success show a state linking to `/bookings` and to
  the trip. Catching `PremiumRequiredError` opens `UpgradeDialog`, composed from `Modal` the way
  `ConfirmDialog` is. Always render the Book button regardless of tier. Add `/flights` and
  `/hotels` to `NAV_LINKS`, and add every new string to both message files under new `Flights` and
  `Hotels` namespaces plus the `Nav` entries.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/app/flights/page.test.tsx src/app/hotels/page.test.tsx src/messages.parity.test.ts`
- **Done:** Both pages search, list results, open the book dialog, show a success state, and open
  the upgrade dialog on a 403; both appear in the nav; the locale files stay at parity.
- **Criteria:** SC-9, SC-11
- **Interfaces:** Consumes the hooks from Task 4.2 and the cards from Task 4.1. Produces `apps/web/src/app/flights/page.tsx`, `apps/web/src/app/hotels/page.tsx`, and `apps/web/src/components/booking/UpgradeDialog.tsx`.

### Task 6.1 — Trip Bookings tab and the two budget totals (wave 6)

- **Files:** apps/web/src/app/trips/[tripId]/page.tsx, apps/web/src/components/trips/bookings/BookingsTab.tsx, apps/web/src/components/trips/budget/BudgetTab.tsx, apps/web/src/components/bookings/BookingTable.tsx, apps/web/src/components/bookings/BookingDetailModal.tsx, apps/web/messages/en.json, apps/web/messages/vi.json, apps/web/src/components/trips/bookings/BookingsTab.test.tsx, apps/web/src/components/trips/budget/BudgetTab.test.tsx
- **Action:** Add a `BookingsTab({ tripId })` following the contract in `ExpensesTab.tsx` — its own
  translations, its own spinner, error and empty ladder inside a `Card`. It lists
  `GET /bookings?trip_id=`, reuses `src/components/bookings/BookingTable.tsx` and
  `BookingDetailModal.tsx` for the rows and the cancel affordance, and links to `/flights?tripId=`
  and `/hotels?tripId=`. Change those two shared components only if the tab genuinely needs it
  (for example to drop a redundant column); leave their existing call site in `/bookings` working. Register it in
  the `Tab[]` list on the trip page. In `BudgetTab`, show `booked_total` beside `total_spent` with
  distinct labels: `total_spent` is what is counted in the itinerary, `booked_total` is what is
  booked for this trip. Add all new keys to both message files under `TripDetail.tabs` and the
  budget namespace.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/trips/bookings/BookingsTab.test.tsx src/components/trips/budget/BudgetTab.test.tsx src/messages.parity.test.ts`
- **Done:** The trip page shows a Bookings tab listing only that trip's bookings, with cancel and
  links carrying `tripId`; the Budget tab shows both totals under labels that distinguish them;
  the locale files stay at parity.
- **Criteria:** SC-10, SC-11
- **Interfaces:** Consumes the trip filter from Task 3.1 and `booked_total` from Task 3.2. Produces `apps/web/src/components/trips/bookings/BookingsTab.tsx`.

### Task 7.1 — Booking end-to-end smoke and the lint sweep (wave 7)

- **Files:** apps/web/playwright/booking-smoke.spec.ts
- **Action:** Add an opt-in Playwright spec that starts from the stored auth state the way
  `playwright/trip-smoke.spec.ts` does, visits `/flights`, searches, books, and asserts the booking
  appears on the trip's Bookings tab. Skip it at file scope when credentials are absent, matching
  `auth.setup.ts`, so a run without credentials collects the spec and skips it rather than failing.
  Then run the project-wide typecheck and the backend linter as the final gate. Expect no edits:
  each task fixes its own lint and types under Rule 3. If either tool reports something, fix it in
  the file the owning task declared and record the deviation there rather than editing outside
  this task's Files set.
  Note: this task is an addition beyond design §5 S1, which named no end-to-end test. It is kept
  because S1 is the first slice that can be exercised end to end, and the repo's Playwright suite
  is opt-in so it costs no CI time.
- **Verify:** `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec playwright test --list playwright/booking-smoke.spec.ts && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec tsc --noEmit && cd ../api && ../../.venv/bin/ruff check app`
- **Done:** Playwright lists the booking spec without a collection error, `tsc --noEmit` exits 0,
  and `ruff check app` exits 0.
- **Criteria:** SC-12, SC-13, SC-14
- **Interfaces:** Consumes the finished pages and routes. Produces `apps/web/playwright/booking-smoke.spec.ts`.

## 5. Risks

- **Stale local database.** Any ORM schema change makes an existing `travel.db` fail the whole
  suite until it is rebuilt, and a seed-default change stays invisible on an old file. Rebuild the
  local database after Task 1.2 before trusting any later Verify.
- **Docker Python 3.12 versus local 3.14.** Run `make test-docker` before shipping; annotation
  evaluation and Postgres ordering differ from the local run.
- **Panel test fragility.** `FlightsPanel.test.tsx` sets `process.env.TZ` on line 3, before its
  imports. Task 4.1 must not reorder imports in the test file or the UTC assertions drift.
- **Risk-corroboration gate.** The diff touches authorization, a migration, and public contracts.
  The lane is already declared `high-risk` in `SUMMARY.md`, which is what the hook corroborates
  against; do not lower it.
- **`pnpm gen:api` needs a running API.** Task 4.2's regeneration step requires the API on port
  8000; without it the typed 403 is missing and SC-12 fails for a reason unrelated to the code.
- **Idempotency change is silent.** Adding the two paths to the whitelist has no test of its own
  beyond the mutation test; a regression would only show as duplicate bookings under a double
  click.

## 6. Status Log

| Date | Event |
|---|---|
| 2026-09-08 | Plan written from the approved design §5 S1 and the Deep research brief. Status `proposed`. |
| 2026-09-08 | Plan reviewed twice by an independent reviewer; five issues fixed, then approved. Typecheck moved from Task 4.2 to Task 7.1 so it cannot read a sibling's mid-edit files. |
| 2026-09-08 | Wave 1 executed: tasks 1.1, 1.2 complete; commit 2c828ea. Both Verify commands re-run by the controller, exit 0; alembic reports one head. |
| 2026-09-08 | Task 1.3 complete; commit e3ba3cd. All nine test files that post a book route pass (228 tests). Remaining tests/api failures are pre-existing dashboard basic-auth 401s from `apps/api/.env`. |
| 2026-09-08 | Wave 2 complete: task 2.1; commit 179a428. |
| 2026-09-08 | Pushed; PR #167 opened → main at bb31851. Run state `ready_to_merge`. |
| 2026-09-08 | Post-review delta (889b189, 7b7bc87, 032aa96) re-reviewed independently: pass, 0 blocking. The receipt is pinned at 032aa96, the true reviewed head. Targeted backend suite 387 passed; frontend 249 passed, typecheck and eslint clean. |
| 2026-09-08 | Final review chain: correctness pass (7 findings, none blocking), intent pass (all 12 design items shipped, no drift). Fixes in commit 889b189, incl. a real double-booking path. Postgres suite run: 2252 passed, zero failures in this slice's areas. Receipt pinned at 889b189. |
| 2026-09-08 | Wave 7 complete: task 7.1; commit 9f643de. All 10 tasks done. `verify_summary.py --check` re-ran all 15 SUMMARY Verify commands: every one exit 0. |
| 2026-09-08 | Wave 6 complete: task 6.1; commit 4767b16. 242 frontend tests green, typecheck clean. |
| 2026-09-08 | Wave 5 complete: task 5.1; commit c95a90e. 237 frontend tests green, typecheck clean. |
| 2026-09-08 | Wave 4 complete: tasks 4.1, 4.2; commit 3edf18b. Whole frontend suite green: 229 tests across 41 files. |
| 2026-09-08 | Wave 3 complete: tasks 3.1, 3.2; commit 2b5d574. Verifies ran over the whole enclosing directory: 65 tests in tests/api/booking, 104 in tests/api/trip. Backend half of the slice is done. |
| 2026-09-08 | Task 2.1 complete but its file-scoped Verify hid a session-scoped DB collision with an existing test; fix dispatched. Task Verify for 3.1 and 3.2 widened to the enclosing directory (52s and 43s) so the same class of miss cannot repeat. |
| 2026-09-08 | Wave 1 review: spec pass, quality needs_fixes. Critical — the gate regressed 89 pre-existing route tests, invisible to both file-scoped Verifies. Fix dispatched as task 1.3. Important — 1.2's repository mapping is inert until task 2.1 adds `trip_id` to the Booking schema; 2.1 now carries a round-trip assertion. |
