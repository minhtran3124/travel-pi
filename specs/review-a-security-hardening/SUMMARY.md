# review-a-security-hardening — Summary

Lane: high-risk
Confidence: high
Reason: hard gates fired — auth (anonymous identity path removed from /agent/*), authorization (owner scoping for bookings and saved places), data-loss/migration (destructive revision adding NOT NULL user_id), public-contract (unauthenticated routes become 401; dashboard becomes gated). Direction ambiguity was resolved by the human at intake (ESCALATIONS.md E001–E004), so confidence is high.
Flags: auth, authorization, data model, audit/security, public contracts, existing behavior, multi-domain
Affects: apps/api/app/routers/agent.py, bookings.py, places.py, flights.py, hotels.py, dashboard*.py; app/db/models/booking.py, saved_place.py (+ alembic); app/tools/{flight,hotel,booking}_tools.py; apps/web chat identity
Input-type: change request
Route: high-risk — design.md (this dir) → research-brief.md → PLAN.md → using-git-worktrees → subagent-driven-development
Escalate: no (E001–E004 decided at intake by the human; see ESCALATIONS.md)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> make the spec/plan /feature-intake cho phần "A. Sửa ngay (bug & bảo mật)" trước.
>
> (from docs/reviews/2026-09-02-deep-review.md §3.A, items 2–3; item 1 is split into
> `specs/fix-reflection-synthesize-goto/`, item 4 was withdrawn as a false positive)
>
> 2. Endpoint agent tin `user_id` ẩn danh từ client — BẢO MẬT. Không token thì `body.user_id` là
> identity; conversations, memory store (namespace theo user_id) và quota dựa vào nó. Ai cũng
> đọc/claim conversation + memory của anon user khác; quota bypass bằng xoay id. Rate-limit
> primitive (#110) đã build nhưng chưa wire vào router nào.
>
> 3. Bookings & saved places không owner; dashboard không auth — BẢO MẬT. Ownership (#118) chỉ cho
> trips/expenses. `Booking`, `SavedPlace` không có `user_id`: ai cũng đọc/hủy booking theo id. 19
> trang `/dashboard/*` đổi được model mọi sub-agent, tắt reflection, không cần đăng nhập.
>
> Intake decisions (AskUserQuestion, 2026-09-02): anonymous path → "Bắt buộc đăng nhập cho
> /agent/*"; ownership data → "Xóa rows cũ, NOT NULL"; dashboard → "Tắt ở production + HTTP Basic";
> MCP booking tools → "Chấp nhận, bỏ khỏi MCP".

## What changed

Closed the three identity holes from the 2026-09-02 deep review, across four waves:

- **Auth on the agent.** Every `/agent/*` route except `/manifest` now requires a Supabase JWT
  (`CurrentUserDep`); the anonymous client-supplied `user_id` is ignored. The web chat drops its
  localStorage anonymous identity, gates on the Supabase session, and keeps a one-shot claim of any
  legacy anonymous history on first sign-in.
- **Ownership.** `Booking` and `SavedPlace` gain a `NOT NULL` indexed `user_id` (destructive
  revision `c7f1a9d4e6b2`, deleting ownerless rows), and the repositories, services, REST routes,
  and agent tools are owner-scoped on the #118 pattern (a foreign id resolves to not-found, never a
  403 oracle). This also closed the pre-existing "cancel any booking by id" hole and two agent
  cross-user saved-place reads (`resolve_place` and the trip-shortlist path).
- **Dashboard + MCP.** `/dashboard/*` is 404 in production without credentials and behind HTTP Basic
  when configured; destructive booking/cancellation tools are excluded from the unauthenticated MCP
  surface.

### Rationale

Three holes share one root cause: identity is optional or absent on write paths. The fix makes the
JWT subject the only identity on `/agent/*`, stamps that identity onto bookings and saved places
(schema + repository + router + agent tool), and puts the operator dashboard behind an
environment-aware guard. Decisions were narrowed by the human before planning so the plan is
executable without further interruption.

### Alternatives considered

- Keep anonymous chat + rate-limit by IP/subject (lowest blast) — rejected by the human at intake
  in favour of requiring login (E001).
- Nullable `user_id` keeping legacy rows — rejected (E002); repeat the #118 pattern instead.
- Admin-JWT cookie login for the dashboard — rejected (E003) as a new auth feature; basic auth +
  production-off is enough for an operator tool.
- Keep book/cancel over MCP via an explicit `user_id` parameter — rejected (E004): it re-creates the
  spoof this spec closes.

### Deviations

- Rule 2 (task 1.2): added a one-line `HTTPException.headers` forward in `app/core/errors.py` (outside
  the task's files) so the dashboard's `401 WWW-Authenticate: Basic` challenge reaches the client.
- Rule 3 (task 2.1): threaded the owner into `trip_service`'s two booking reads and added unscoped
  dashboard reads — a plan gap (no task owned booking↔trip reads); the trip suite stays green.
- Controller: corrected E004's mechanism — `InjectedState` does not drop a tool off MCP, so the
  destructive-tool exclusion is an explicit filter in `app/mcp/server.py` (+ tests) rather than an
  automatic consequence of injection. Added `specs/review-a-security-hardening` Task 3.2 + SC-8 after
  a wave-2 review found the `resolve_place` saved-read leak; a wave-3 review found the sibling
  `add_place_to_trip` leak, fixed in `d4397d4`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Agent JWT required | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc1.db ../../.venv/bin/python -m pytest tests/api/agent/test_agent_auth_required.py -q` | 0 | 401 without a token; body user_id ignored | SC-1 |
| Booking cross-user 404 | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc2.db ../../.venv/bin/python -m pytest tests/api/booking/test_booking_ownership.py -q` | 0 | B cannot read/cancel/list A's bookings | SC-2 |
| Saved-place cross-user 404 | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc3.db ../../.venv/bin/python -m pytest tests/api/place/test_saved_place_ownership.py -q` | 0 | B cannot read/delete/toggle/list A's saved places | SC-3 |
| Dashboard guard states | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc4.db ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q` | 0 | 404 in prod / 401 / 200 / dev-open | SC-4 |
| Owner migration reversible | `cd apps/api && env DATABASE_URL=sqlite:///$(mktemp -d)/sc5.db sh -c '../../.venv/bin/alembic upgrade head && ../../.venv/bin/alembic downgrade -1 && ../../.venv/bin/alembic upgrade head'` | 0 | upgrade→downgrade→upgrade clean | SC-5 |
| Agent booking stamps owner | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc6.db ../../.venv/bin/python -m pytest tests/tools/test_booking_owner.py -q` | 0 | injected owner; 4 tools absent from MCP | SC-6 |
| FE signed-out gate | `cd apps/web && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm vitest run src/components/chat/ChatWidget.auth.test.tsx src/lib/api/client.test.ts` | 0 | sign-in prompt, no request, no X-User-Id | SC-7 |
| Agent saved-read scoped | `cd apps/api && env -u OPENAI_API_KEY DATABASE_URL=sqlite:///$(mktemp -d)/sc8.db ../../.venv/bin/python -m pytest tests/tools/test_place_owner.py -q` | 0 | resolve_place + shortlist owner-scoped | SC-8 |

### Not auto-verified

- Existing dev/prod databases lose all `bookings` and `saved_places` rows on upgrade — reached
  traceability (documented in the migration docstring and PLAN §5); not re-run against any
  non-test database. Take a backup before `alembic upgrade head` where rows matter.
- Two pre-existing `tests/tools/test_routing_tools.py` offline-estimate failures are unrelated to
  this branch (routing was untouched; verified they fail identically on the branch base) — provenance,
  not re-fixed.
- Follow-up (final correctness review, Minor, not fixed): owner-scoped READ tools that inject
  `user_id` (`resolve_place`, `get_trip_summary`, `get_trip_budget`, `list_trip_places`,
  `recall_past_trips`) remain on the MCP surface, where `user_id` becomes a client-supplied param
  (MCP has no ToolNode injection). An MCP client that knows a victim's opaque Supabase UUID could
  read that user's data. Severity is low — a pre-existing pattern this branch only tightened
  (`resolve_place` was previously fully unscoped over MCP), the MCP server is stdio-only and not
  mounted in the app, and the exploit needs the victim's UUID. Destructive book/cancel tools ARE
  excluded. A follow-up spec should exclude owner-scoped read tools from MCP too (or make the MCP
  surface ignore client-supplied injected args).
- Deferred minor (wave-3 review): the injected `user_id` defaults to `""`; the wave-1 JWT requirement
  guarantees a real id on every `/agent/*` turn, so it is not reachable, but a guard would be sturdier.

### Rollback

- Code: `git revert <sha>` per commit.
- Schema: `cd apps/api && ../../.venv/bin/alembic downgrade -1` restores the columns' absence but
  **cannot restore deleted rows** — take a DB backup before `upgrade head` anywhere rows matter.

### Harness-Delta

- backlog: `hooks/lib/lane.sh` assumes a single `status: active` plan and takes the first by glob
  order; 11 stale actives made risk-corroboration read the wrong lane. Flipping shipped plans
  unblocked it (`f8c1071`), but the resolver should disambiguate (e.g. STATE.md active slug).
- backlog: `commit-quality-gate.sh` secrets scan excludes `tests/` but the pathspec `:!tests/` misses
  the monorepo's `apps/api/tests/`, so a test password literal false-positives (hit here on
  `_PASSWORD = "s3cret"`).
- backlog: the PLAN wave-2 partition missed the `trip_service` booking-read and saved-read
  integration points, surfaced only by the service-layer suite and the wave-3 review.
