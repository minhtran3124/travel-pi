# review-a-security-hardening — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

All four blocks below were raised and decided at intake (AskUserQuestion, interactive session,
2026-09-02) before any implementation edit.

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-02
- trigger: hard-gate
- question: How should the anonymous identity path on `/agent/*` (client-supplied `user_id`) be closed?
- context: blocks every task touching `apps/api/app/routers/agent.py` and the web chat identity.
- options:
  - A) Keep anonymous chat; wire the existing `rate_limit` dependency by IP + subject on `/agent/chat|stream|conversations`.
  - B) Server-signed anonymous session token; reject self-declared ids.
  - C) Require a Supabase JWT on every `/agent/*` route; remove anonymous chat.
- default_if_no_response: BLOCK
- decision: C — require login for `/agent/*`. `POST /agent/conversations/claim` stays (already auth-only) so a legacy localStorage id can still be claimed once after sign-in.
- decided_by: Minh Tran
- decided_at: 2026-09-02

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-02
- trigger: hard-gate
- question: When adding `user_id` to `bookings` and `saved_places`, what happens to existing rows?
- context: blocks the migration task (wave 1).
- options:
  - A) Delete all existing rows, add the column `NOT NULL` in one revision (the #118 pattern, `a4d8e2c6b013`).
  - B) Add the column nullable and keep legacy rows as ownerless orphans.
- default_if_no_response: BLOCK
- decision: A — destructive revision; rows have no owner to backfill from.
- decided_by: Minh Tran
- decided_at: 2026-09-02

## E003

- raised_by: orchestrator (feature-intake)
- date: 2026-09-02
- trigger: hard-gate
- question: How is `/dashboard/*` (server-rendered Jinja, no browser JWT) protected?
- context: blocks the dashboard guard task.
- options:
  - A) Return 404 for `/dashboard/*` when `environment=production` unless `DASHBOARD_BASIC_USER`/`DASHBOARD_BASIC_PASSWORD` are set; when set (any environment) require HTTP Basic; dev without credentials stays open.
  - B) Only disable in production.
  - C) Admin-JWT cookie login page.
- default_if_no_response: BLOCK
- decision: A.
- decided_by: Minh Tran
- decided_at: 2026-09-02

## E004

- raised_by: orchestrator (feature-intake)
- date: 2026-09-02
- trigger: hard-gate (remove-functionality)
- question: `book_flight` / `book_hotel` / `cancel_flight` / `cancel_hotel` will take `user_id` via `InjectedState` and therefore drop off the MCP server (which skips injected-arg tools). Accept?
- context: blocks the agent-tool task; MIN-42 (PR #80) deliberately exposed these over MCP.
- options:
  - A) Accept the removal; document in FEATURES.md / CHANGELOG; revisit when MCP carries identity (OAuth per MCP 2025-11-25 spec).
  - B) Keep MCP variants that take `user_id` as a plain parameter.
- default_if_no_response: BLOCK
- decision: A — accepted; the MCP server has no auth, so exposing booking there was itself a hole.
- decided_by: Minh Tran
- decided_at: 2026-09-02
