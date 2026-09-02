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

_(pending — written at implementation)_

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

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| <unit> | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_auth_required.py -q` | — | not yet run | SC-1 |

### Not auto-verified

- Existing dev/prod databases lose all `bookings` and `saved_places` rows on upgrade — reached
  traceability (documented in the migration docstring and PLAN §5); not re-run against any
  non-test database.

### Rollback

- Code: `git revert <sha>` per commit.
- Schema: `cd apps/api && ../../.venv/bin/alembic downgrade -1` restores the columns' absence but
  **cannot restore deleted rows** — take a DB backup before `upgrade head` anywhere rows matter.

### Harness-Delta

- backlog: the deep-review agent reported "PII in tool logs" from docstring line ranges that never
  reached a logger; a reviewer claim about logging should be corroborated by a `grep` on
  `logger|log_tool_call` before it enters a findings list (→ compound).
