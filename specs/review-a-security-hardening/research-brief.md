# review-a-security-hardening — Research brief

Depth: **Deep** (intake lane high-risk → Deep per `rules/research-depth.md`). No upgrade needed.

## What already exists (reuse)

| Need | Existing seam | Evidence |
|---|---|---|
| Required-auth dependency | `CurrentUserDep` / `get_current_user` (401 on missing/invalid JWT) | `app/core/auth.py:115`; used by `routers/trips.py`, `expenses.py`, `admin.py` |
| Owner-scoped repository pattern | `TripRepository` (`user_id` on every method, foreign id → `None` → 404) | `app/repositories/trip.py`, `specs/gh-118-trip-ownership/PLAN.md` Task 2.1 |
| Destructive owner migration | `a4d8e2c6b013_add_trips_user_id.py` (delete rows, add NOT NULL column, log counts, batch_alter_table) | `apps/api/alembic/versions/` |
| Injected identity in tools | `memory_tools.py` uses `user_id: Annotated[str, InjectedState("user_id")]`; `TravelAgentState.user_id` exists | `app/tools/memory_tools.py:37`, `app/agents/state.py:93` |
| Injected-arg guard derived from annotations | `_tools_needing_trip` in `subagents/_base.py:72-112` — same introspection can confirm the four booking tools now carry `user_id` | `_base.py` |
| MCP skips injected tools | `mcp/server.py:39-42` | confirms E004 consequence without code change |
| Environment flag | `Settings.environment` / `is_production` | `app/core/config.py:51,236` |
| Basic-auth primitive | `fastapi.security.HTTPBasic` + `secrets.compare_digest` (stdlib) | FastAPI ≥0.110 pinned; API stable |
| Anonymous history claim | `POST /agent/conversations/claim` (auth-only, refuses registered ids) | `routers/agent.py:564-610`; `tests/api/agent/test_claim.py` |
| Web session source | `UserMenu.tsx` `getUser()` + `onAuthStateChange`; `useAgentStream` already calls `supabase.auth.getSession()` for claim | `apps/web/src/components/chat/useAgentStream.ts:205-254` |

## What is missing

- No owner column on `bookings` / `saved_places`; no auth dependency on their routers or on
  `POST /flights/book`, `POST /hotels/book`.
- No dashboard guard of any kind; `include_in_schema=False` is the only "protection".
- Web has no shared session hook; `lib/identity/provider.tsx` mints a localStorage UUID and the API
  client sends it as `X-User-Id` (documented as "NOT what the BE scopes on").
- No negative (cross-user) tests for bookings/saved places; `tests/api/agent/test_identity_hybrid.py`
  asserts the anonymous behaviour that E001 removes and must be rewritten, not deleted silently.

## Lightest credible path

Follow #118 exactly, one layer per wave: schema → data access → routers/tools → web → cross-user
tests. Do not introduce a generic "ownable" mixin; two models do not justify an abstraction.

## Risks found during research

- `BookingService.book_flight/book_hotel` also serve REST (`flights.py:211`, `hotels.py:275`) and the
  agent tools; both callers must pass `user_id` or the NOT NULL insert fails at runtime.
- Dashboard `/bookings` page lists all bookings (operator view) — keep it unscoped behind the
  dashboard guard; do not accidentally scope it to nobody.
- `tests/conftest.py` fixtures for auth (`auth_headers`-style) exist for trips; reuse them rather
  than minting a second JWT helper.
- `test_identity_hybrid.py` name becomes misleading; rename to `test_agent_auth_required.py` in the
  same task so the SC row points at a real file.

## Source Pack

- none (local-only; no external surface — `HTTPBasic` is a long-stable FastAPI API already in the
  pinned range, no new dependency).
