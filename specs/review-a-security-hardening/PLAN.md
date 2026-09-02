---
slug: review-a-security-hardening
status: active
owner: Minh Tran
created: 2026-09-02
---

# review-a-security-hardening — Close the three identity holes from the 2026-09-02 deep review

**Base:** `main` (`95be73e`). **Branch:** `fix/review-a-security-hardening`.
Decisions E001–E004 are recorded in `ESCALATIONS.md`; design in `design.md`.

## Global Constraints

- Follow the #118 ownership pattern verbatim: repository methods take `user_id`; a foreign id
  resolves to *not found* (404), never 403.
- Every `Verify` and SC check is a single pipe-free command under 60s; never the whole suite.
  The full suite (`make test` then `make test-docker`) runs at `finishing-a-development-branch`.
- Stage and commit as separate commands (PreToolUse hook). No Claude attribution trailers
  (`CLAUDE.local.md`).
- Backend commands run from `apps/api/` with `../../.venv/bin/python`; web commands from
  `apps/web/` with Node 24 on `PATH`.
- Do not touch `app/mcp/server.py`; the MCP consequence (E004) is documentation only.
- Same-wave tasks share no files.

## 1. Motivation

See `design.md` → Problem. Three write surfaces trust or lack identity; all three are reachable
today without a token.

## 2. Non-goals

Rate-limit-by-IP wiring, signed anonymous tokens, booking↔trip linkage, admin-JWT dashboard login,
the reflection routing bug (`specs/fix-reflection-synthesize-goto`).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | `POST /agent/chat`, `POST /agent/stream`, `GET /agent/conversations*` return 401 without a JWT and ignore a body/query `user_id` with one | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_auth_required.py -q` | exit 0 |
| SC-2 | User B cannot list, read, or cancel user A's booking (404); `POST /flights/book` and `POST /hotels/book` require auth and stamp the caller | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_booking_ownership.py -q` | exit 0 |
| SC-3 | Saved places are per-user: B cannot read, delete, favourite or list A's saved places | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/place/test_saved_place_ownership.py -q` | exit 0 |
| SC-4 | `/dashboard/*` is 404 in production without credentials, 401 with credentials configured but absent/wrong, 200 with valid Basic credentials, and open in development | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q` | exit 0 |
| SC-5 | The owner revision applies, downgrades and re-applies cleanly on a fresh SQLite DB | `cd apps/api && env DATABASE_URL=sqlite:///$(mktemp -d)/sc5.db sh -c '../../.venv/bin/alembic upgrade head && ../../.venv/bin/alembic downgrade -1 && ../../.venv/bin/alembic upgrade head'` | exit 0 |
| SC-6 | Bookings created or cancelled through the agent tools carry the graph's `user_id`; the four tools are absent from the MCP tool list | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_booking_owner.py -q` | exit 0 |
| SC-7 | Logged-out web users see a sign-in prompt in the chat widget and no request is sent; `X-User-Id` is no longer attached to any request | `cd apps/web && pnpm vitest run src/components/chat/ChatWidget.auth.test.tsx src/lib/api/client.test.ts` | exit 0 |
| SC-8 | The agent tool `resolve_place(source="saved")` cannot read another user's saved place by id or SPL- short code | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_place_owner.py -q` | exit 0 |

## 4. Tasks

### Task 1.1 — Owner columns and the destructive revision (wave 1)

- **Files:** apps/api/app/db/models/booking.py, apps/api/app/db/models/saved_place.py, apps/api/alembic/versions/new_add_bookings_saved_places_user_id.py
- **Action:** Add `user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)` to
  `Booking` and `SavedPlace`. Write one revision (down_revision = current head) that logs row
  counts, `DELETE FROM bookings` and `DELETE FROM saved_places`, then adds both columns `NOT NULL`
  with `ix_bookings_user_id` / `ix_saved_places_user_id` via `batch_alter_table` (SQLite). Mirror the
  docstring of `a4d8e2c6b013`: DESTRUCTIVE, downgrade restores schema not data, backup first.
  Rebuild the local `travel.db` afterwards (memory: stale-travel-db-breaks-suite-on-schema-change).
- **Criteria:** SC-5
- **Interfaces:** Consumes: the current Alembic head and the two ORM models (external, already present). Produces: `apps/api/app/db/models/booking.py`, `apps/api/app/db/models/saved_place.py`, `apps/api/alembic/versions/new_add_bookings_saved_places_user_id.py`.
- **Verify:** `cd apps/api && env DATABASE_URL=sqlite:///$(mktemp -d)/t11.db sh -c '../../.venv/bin/alembic upgrade head && ../../.venv/bin/alembic downgrade -1 && ../../.venv/bin/alembic upgrade head'`
- **Done:** both columns exist, NOT NULL, indexed; upgrade→downgrade→upgrade is clean on SQLite.

### Task 1.2 — Dashboard guard (wave 1)

- **Files:** apps/api/app/core/dashboard_auth.py, apps/api/app/core/config.py, apps/api/app/routers/dashboard.py, apps/api/app/routers/dashboard_prompts.py, apps/api/tests/api/agent_config/test_dashboard_auth.py
- **Action:** Add settings `dashboard_basic_user: str | None = None` and
  `dashboard_basic_password: str | None = None`. Create `require_dashboard_access(request,
  credentials=Depends(HTTPBasic(auto_error=False)))`: if credentials are configured, compare both
  with `secrets.compare_digest` and raise 401 with `WWW-Authenticate: Basic` on mismatch/absence;
  else if `settings.is_production`, raise 404; else allow. Attach as
  `dependencies=[Depends(require_dashboard_access)]` on both dashboard routers (covers
  `/_search.json` and the agent-config POST). Tests cover the four states in SC-4 using the existing
  settings override fixture.
- **Criteria:** SC-4
- **Interfaces:** Consumes: Settings.is_production (existing config, external). Produces: `apps/api/app/core/dashboard_auth.py`, `apps/api/tests/api/agent_config/test_dashboard_auth.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py tests/api/agent_config -q`
- **Done:** SC-4 states pass; existing agent-config dashboard tests still pass in development mode.

### Task 1.3 — Require a JWT on every `/agent/*` route (wave 1)

- **Files:** apps/api/app/routers/agent.py, apps/api/tests/api/agent/test_agent_auth_required.py, apps/api/tests/api/agent/test_identity_hybrid.py, apps/api/tests/api/agent/test_agent_chat.py, apps/api/tests/api/agent/test_stream_persistence.py, apps/api/tests/api/agent/test_quota.py, apps/api/tests/api/agent/test_agent_history.py
- **Action:** Replace `OptionalUserDep` with `CurrentUserDep` on `/chat`, `/stream`,
  `GET /conversations`, `GET /conversations/{id}`, and messages; use `auth_user.id` directly and
  delete the anonymous fallback branch of `_effective_user_id` (keep the helper only if a caller
  remains). Keep `ChatRequest.user_id` optional-and-ignored for one release (document as deprecated
  in the schema description) so old clients get 401 rather than 422. Leave
  `POST /conversations/claim` and `/manifest` unchanged. Move the anonymous-path assertions from
  `test_identity_hybrid.py` into `test_agent_auth_required.py` (401 without token; body `user_id`
  ignored with token; quota keyed on the JWT sub) and delete the old file. Update the other listed
  tests to send the existing auth fixture instead of a raw `user_id`.
- **Criteria:** SC-1
- **Interfaces:** Consumes: CurrentUserDep from app/core/auth.py (existing, external). Produces: `apps/api/app/routers/agent.py`, `apps/api/tests/api/agent/test_agent_auth_required.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent -q`
- **Done:** no `/agent/*` route except `/manifest` answers without a valid JWT; all agent API tests pass.

### Task 2.1 — Scope bookings end to end (wave 2)

- **Files:** apps/api/app/repositories/booking.py, apps/api/app/services/booking_service.py, apps/api/app/routers/bookings.py, apps/api/app/routers/flights.py, apps/api/app/routers/hotels.py, apps/api/app/schemas/booking.py, apps/api/tests/api/booking/test_bookings.py, apps/api/tests/api/flight/test_flights.py, apps/api/tests/api/hotel/test_hotels.py
- **Action:** `BookingRepository.get/get_by_confirmation_code/list_all/update_status` take
  `user_id` and filter on it; `add` stamps it; idempotency replay is looked up per owner.
  `BookingService.get/list_all/cancel/query/book_flight/book_hotel` take `user_id` (keyword-only).
  Add `CurrentUserDep` to `GET /bookings`, `GET /bookings/{id}`, `POST /bookings/{id}/cancel`,
  `POST /flights/book`, `POST /hotels/book` and pass `auth_user.id`. Expose `user_id` on the
  booking response schema only if the FE needs it (default: do not). Update existing tests to
  authenticate; keep the dashboard `/bookings` page on an explicit `list_all_unscoped()` used by the
  dashboard only.
- **Criteria:** SC-2
- **Interfaces:** Consumes: `apps/api/app/db/models/booking.py` (Task 1.1) and CurrentUserDep (existing). Produces: `apps/api/app/services/booking_service.py`, `apps/api/app/repositories/booking.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking tests/api/flight tests/api/hotel -q`
- **Done:** every booking read/write path requires an owner; existing booking/flight/hotel tests pass authenticated.

### Task 2.2 — Scope saved places end to end (wave 2)

- **Files:** apps/api/app/repositories/saved_place.py, apps/api/app/services/saved_place_service.py, apps/api/app/routers/places.py, apps/api/tests/api/place/test_saved_places.py
- **Action:** `SavedPlaceRepository.get/list/soft_delete/set_flag/find_duplicate` take `user_id`;
  `add` stamps it. `SavedPlaceService` threads it. Add `CurrentUserDep` to the six saved-place
  routes in `places.py` (`/places/saved*`) only; catalog routes stay public. Update existing tests
  to authenticate.
- **Criteria:** SC-3
- **Interfaces:** Consumes: `apps/api/app/db/models/saved_place.py` (Task 1.1). Produces: `apps/api/app/services/saved_place_service.py`, `apps/api/app/repositories/saved_place.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/place -q`
- **Done:** saved-place routes 401 without a token and never return another user's rows.

### Task 2.3 — Web: session-gated chat, no anonymous identity (wave 2)

- **Files:** apps/web/src/lib/identity/provider.tsx, apps/web/src/lib/api/client.ts, apps/web/src/components/chat/useAgentStream.ts, apps/web/src/components/chat/ChatWidget.tsx, apps/web/src/messages/en.json, apps/web/src/messages/vi.json, apps/web/src/components/chat/ChatWidget.auth.test.tsx, apps/web/src/lib/api/client.test.ts
- **Action:** Replace the localStorage UUID in `provider.tsx` with the Supabase session user id
  (subscribe via `onAuthStateChange`; expose `{ userId, status: 'loading' | 'signed-out' |
  'signed-in' }`). Remove the `X-User-Id` header from `client.ts`. In `useAgentStream`, do not send
  or hydrate while signed out; keep the one-shot legacy claim (read the old localStorage key, POST
  `/agent/conversations/claim`, then clear it). `ChatWidget` renders a signed-out state — copy
  "Sign in to chat with Tin" / "Đăng nhập để trò chuyện với Tin" — linking to `/auth/login`.
  Add the two tests named in SC-7; keep en/vi key parity (`messages.parity.test.ts`).
- **Criteria:** SC-7
- **Interfaces:** Consumes: the Supabase browser client and existing i18n message files (external). Produces: `apps/web/src/lib/identity/provider.tsx`, `apps/web/src/components/chat/ChatWidget.tsx`, `apps/web/src/components/chat/ChatWidget.auth.test.tsx`, `apps/web/src/lib/api/client.test.ts`.
- **Verify:** `cd apps/web && pnpm vitest run src/components/chat src/lib`
- **Done:** logged-out users see the prompt and no `/agent/*` request is made; chat works unchanged when signed in.

### Task 3.1 — Agent tools stamp the owner (wave 3)

- **Files:** apps/api/app/tools/flight_tools.py, apps/api/app/tools/hotel_tools.py, apps/api/app/tools/booking_tools.py, apps/api/tests/tools/test_booking_owner.py, apps/api/tests/tools/test_flight_booking_tool.py, apps/api/tests/tools/test_hotel_tools.py, apps/api/tests/tools/test_cancel_tools.py, apps/api/tests/tools/test_tool_registry.py, FEATURES.md, apps/api/app/prompts/CHANGELOG.md
- **Action:** Add `user_id: Annotated[str, InjectedState("user_id")]` to `book_flight`, `book_hotel`,
  `cancel_flight`, `cancel_hotel` (annotation-derived schema only — never an explicit
  `args_schema`, per docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md) and pass it
  to `BookingService`. Do not log it. Add `tests/tools/test_booking_owner.py` asserting the created
  booking's `user_id` equals the state's and that `mcp/server.py`'s tool list no longer contains the
  four names. Update FEATURES.md §2.4/§8 and the prompts CHANGELOG with the E004 note.
- **Criteria:** SC-6
- **Interfaces:** Consumes: `apps/api/app/services/booking_service.py` (Task 2.1) and TravelAgentState.user_id (existing). Produces: `apps/api/tests/tools/test_booking_owner.py`, `apps/api/app/tools/booking_tools.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/tools -q`
- **Done:** agent-made bookings carry the owner; MCP manifest excludes the four tools; tool tests pass.

### Task 3.2 — Scope the agent saved-place read (wave 3)

- **Files:** apps/api/app/tools/place_tools.py, apps/api/app/services/place_service.py, apps/api/app/repositories/saved_place.py, apps/api/tests/tools/test_place_owner.py
- **Action:** Surfaced by the wave-2 review (rev-2-2, Important): `resolve_place(source="saved")` →
  `PlaceService.resolve` → `SavedPlaceRepository.get(place_id)` runs with no owner, so an LLM-invoked
  tool with a user-controlled `place_id`/`SPL-` short code reads any user's saved place (name,
  address, coords, notes = PII); the short-code branch scans all users' rows. Thread
  `user_id: Annotated[str, InjectedState("user_id")]` into `resolve_place` (annotation-derived schema
  only — never an explicit `args_schema`) and pass it through `PlaceService.resolve`/`.get` into
  `SavedPlaceRepository.get(place_id, user_id=...)` for the saved source; the short-code scan must be
  owner-filtered. The agent runs under the authenticated JWT sub (wave 1), so the owner is always
  available. Correct the `SavedPlaceRepository.get` docstring (the None path is NOT internal-only).
  Leave the catalog `source` branch (non-saved) unchanged — it reads public data.
- **Criteria:** SC-8
- **Interfaces:** Consumes: `apps/api/app/repositories/saved_place.py` (Task 2.2) and TravelAgentState.user_id (existing). Produces: `apps/api/tests/tools/test_place_owner.py`, `apps/api/app/tools/place_tools.py`.
- **Verify:** `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL="sqlite:///$(mktemp -d)/t32.db" ../../.venv/bin/python -m pytest tests/tools/test_place_owner.py tests/tools/test_place_tools.py -q`
- **Done:** user B's agent cannot resolve A's saved place by id or SPL- code; catalog resolves unchanged.

### Task 4.1 — Cross-user negative tests and API docs (wave 4)

- **Files:** apps/api/tests/api/booking/test_booking_ownership.py, apps/api/tests/api/place/test_saved_place_ownership.py, apps/api/APIS.md, apps/api/.env.example
- **Action:** Write the tests SC-2 and SC-3 point at: two authenticated users; B gets 404 on A's
  booking (`GET`, `cancel`, by confirmation code) and on A's saved place (`GET`, `DELETE`,
  favourite/visited); list endpoints return only the caller's rows; unauthenticated → 401. Document
  the auth requirement and the two dashboard settings in `APIS.md` / `.env.example`.
- **Criteria:** SC-2, SC-3
- **Interfaces:** Consumes: `apps/api/app/services/booking_service.py` (Task 2.1) and `apps/api/app/services/saved_place_service.py` (Task 2.2). Produces: `apps/api/tests/api/booking/test_booking_ownership.py`, `apps/api/tests/api/place/test_saved_place_ownership.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/booking/test_booking_ownership.py tests/api/place/test_saved_place_ownership.py -q`
- **Done:** all negative cases pass; docs list every route that now requires a token.

## 5. Risks

- **Data loss on upgrade** (E002): every environment loses `bookings` and `saved_places` rows. The
  revision logs counts; operators must back up first. Rollback restores schema only.
- **Anonymous users lose chat** (E001): product change; the FE signed-out state must be visible,
  not a silent failure (deep review §3.C.11 already flags silent 403s).
- **Test churn**: ~150 existing tests assume unscoped access; wave 2 tasks own their test files to
  avoid shared-file races (memory: wave-shared-file-partition).
- **Postgres parity**: run `make test-docker` before opening the PR (`docker-test-compose-shares-project-name`).
- **risk-corroboration hook**: the diff trips auth/authorization/migration/public-contract; Lane is
  declared `high-risk` in SUMMARY.md so the hook corroborates instead of blocking.

## 6. Status Log
- 2026-09-02 — tasks 1.1, 1.2, 1.3 complete; commit 45b1631 (wave 1). travel.db rebuilt to head c7f1a9d4e6b2. Deviations: 1.2 added a one-line HTTPException.headers forward in app/core/errors.py (Rule 2, needed for the 401 Basic challenge); 1.3 also touched app/schemas/agent.py (ChatRequest.user_id deprecated/ignored).
- 2026-09-02 — wave 1 reviewed: all three tasks SPEC+QUALITY PASS (independent reviewers). Minor fixes in 048fb5e (migration filename → convention; dashboard_auth non-ASCII credential → 401 not 500, +regression test). Deferred minors: prod data-loss runbook note (1.1), deprecated ChatRequest.user_id removal next release (1.3).

- 2026-09-02 — intake complete (feature-intake); E001–E004 decided by the human; plan proposed, not yet executed.

- 2026-09-02 — tasks 2.1, 2.2, 2.3 complete; commit 46614d9 (wave 2). BE combined re-verify 384 passed (booking/flight/hotel/place/trip); FE 162 passed. Deviations: 2.1 threaded owner into trip_service booking reads + added unscoped dashboard reads (plan gap, Harness-Delta backlog); 2.2 left places.py unchanged (auth via service factory, #118 pattern) and kept SavedPlaceRepository.get owner optional for the internal resolve path.
- 2026-09-02 — wave 2 reviewed: 2.1 SPEC PASS / QUALITY FAIL (Critical = the expected cross-wave breakage: agent booking/cancel tool callsites call the now-owner-required BookingService without user_id → fixed by Task 3.1); 2.2 SPEC PASS / QUALITY PASS-with-Important (agent resolve_place saved-read cross-user leak → new Task 3.2 + SC-8); 2.3 SPEC+QUALITY PASS. Minors deferred: FE legacy-claim clears its key on a transient network error (silent history loss; useAgentStream.ts), stale anon comment in query/agent.ts.

- 2026-09-02 — tasks 3.1, 3.2 complete + review follow-ups; commits 83fbeff (wave 3) and d4397d4 (SC-8 sibling-path fix). Combined re-verify 653 passed (2 pre-existing unrelated test_routing_tools offline failures). Controller fixes folded in: MCP now excludes destructive tools (E004 premise was wrong — InjectedState does not drop a tool off MCP; explicit destructive filter in app/mcp/server.py + tests); a wave-2 service-test mock updated to the owner signature. Wave-3 review (rev-3): SC-6 + E004 PASS, injection hidden-from-model confirmed for all 5 tools, cancel/book/MCP solid; one Important (add_place_to_trip sibling saved-read leak) fixed in d4397d4 with cross-user shortlist tests. Deferred minor: injected user_id defaults to "" — guaranteed non-empty by the wave-1 JWT requirement, worth a guard later.
