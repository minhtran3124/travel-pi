---
slug: agent-identity-tier
status: active
owner: Minh Tran
created: 2026-06-28
---

# Agent Identity + Tier Management (make tier real)

> Prereq/sibling of `specs/runtime-context-config/` (branch `feat/agent-mode-tier`, PR #43,
> held un-merged). Tier added there is **inert** because the agent identifies users by an
> anonymous localStorage UUID, not their Supabase id — so the BE `users` table never maps to a
> real user. This plan wires the real identity in and makes tier manageable.

## 1. Motivation (the gap the user found)

- FE sends `body.user_id = localStorage["travel.userId"]` — a random "pseudo-identity"
  (`apps/web/src/lib/identity/provider.tsx`), NOT the Supabase user id.
- `/agent/*` is "no auth enforced" (`routers/agent.py`); it trusts `body.user_id`.
- Supabase JWT verification exists (`app/core/auth.py` → `AuthUser{id=sub, email, role, claims}`)
  but the agent never uses it; FE never sends the token.
- ⟹ `users.user_id` (tier) keys off a throwaway UUID. Tier can never correspond to a real user,
  and there's no way to populate the table or set premium. **Migration is meaningless until the
  agent knows the real user.**

## 2. Decisions (confirmed)

- **Hybrid auth**: a valid Supabase JWT → use the Supabase id (`sub`) + tier from the `users`
  table; no/invalid JWT → anonymous, treated as `free` (today's UX preserved). Premium requires
  being logged in.
- **Tier is BE-owned (self-managed)**, set via **both** a CLI and an admin endpoint.
- Security: when a JWT is present, the agent uses its `sub` and **ignores `body.user_id`** (no
  spoofing). Anonymous callers are always `free` (can't be premium — premium rows are keyed by
  Supabase id).

## 3. Non-goals

- No route-protection overhaul / forced login for the rest of the app.
- No billing/Stripe — tier is set by admin/CLI.
- No change to the mode/quota mechanics from `runtime-context-config` (they consume the
  resolved identity/tier).

## 4. Success Criteria

- Logged-in user: agent turns are attributed to their Supabase id; a `users` row is created on
  first call (default `free`); tier drives gating/quota.
- Anonymous user: chat still works as `free` (no token required).
- A forged `body.user_id` is ignored when a JWT is present.
- Admin can set a user `premium` via CLI and via the admin endpoint; that user then gets
  booking + RAG + unlimited quota.

## 5. Tasks

### Task 1.1 — Hybrid identity on agent endpoints (BE)

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/core/auth.py, apps/api/app/routers/agent.py, apps/api/app/repositories/user.py, apps/api/tests/api/agent/test_identity_hybrid.py</files>
  <action>Add an OPTIONAL current-user dependency in auth.py (e.g. get_current_user_optional): returns AuthUser when a valid Bearer token is present, else None (never 401). In routers/agent.py add an effective-identity helper used by /chat, /stream, /conversations, /conversations/{id}/messages: effective_user_id = auth_user.id if auth_user else body.user_id (or the query user_id for GET). When auth_user is present, IGNORE body.user_id. Use effective_user_id everywhere user_id currently flows (ensure_conversation, append_message, _thread_id, _resolve_context tier lookup, quota). In _resolve_context: tier = UserRepository.get_tier(effective_user_id) only when authenticated; anonymous → "free" without a lookup. On an authenticated call, lazy-upsert a row if absent (UserRepository.ensure_user(user_id) default free) so the table reflects real users. Add ensure_user to UserRepository. Keep behavior identical for anonymous callers.</action>
  <verify>cd apps/api && DATABASE_URL="sqlite:///test_run.db" ../../.venv/bin/python -m pytest tests/api/agent/test_identity_hybrid.py -x; rm -f apps/api/test_run.db</verify>
  <done>Authed call uses JWT sub (ignores forged body.user_id) + lazy-creates a users row; anonymous call works as free; tier resolves from the authed id.</done>
</task>
```

### Task 2.1 — Tier CLI

```xml
<task id="2.1" wave="2">
  <files>apps/api/scripts/set_tier.py, apps/api/tests/scripts/test_set_tier.py</files>
  <action>CLI wrapping UserRepository.upsert_tier: `python scripts/set_tier.py <user_id> <free|premium>` against settings.database_url. Validate tier value; print the resulting row. Follow the style of any existing scripts/ entrypoint.</action>
  <verify>cd apps/api && DATABASE_URL="sqlite:///test_run.db" ../../.venv/bin/python -m pytest tests/scripts/test_set_tier.py -x; rm -f apps/api/test_run.db</verify>
  <done>CLI sets a user's tier; invalid tier rejected.</done>
</task>
```

### Task 2.2 — Admin tier endpoint (role-gated)

```xml
<task id="2.2" wave="2">
  <files>apps/api/app/routers/admin.py, apps/api/app/schemas/admin.py, apps/api/app/main.py, apps/api/tests/api/admin/test_admin_tier.py</files>
  <action>PATCH /admin/users/{user_id}/tier {tier} → UserRepository.upsert_tier, REQUIRES a valid JWT with an admin role claim (use the existing required get_current_user + check AuthUser.role == "admin", else 403). Register the router in main.py. Reuse error_responses. NOTE hard gate: new public+auth endpoint — commit with RISK_WARN_CATEGORIES if blocked.</action>
  <verify>cd apps/api && DATABASE_URL="sqlite:///test_run.db" ../../.venv/bin/python -m pytest tests/api/admin/test_admin_tier.py -x; rm -f apps/api/test_run.db</verify>
  <done>Admin (role=admin JWT) can set tier; non-admin → 403; unauth → 401.</done>
</task>
```

### Task 3.1 — FE sends the Supabase token

```xml
<task id="3.1" wave="3">
  <files>apps/web/src/components/chat/useAgentStream.ts, apps/web/src/lib/api/client.ts, apps/web/src/lib/query/agent.ts, apps/web/src/lib/supabase/authHeader.ts</files>
  <action>When a Supabase session exists (supabase client getSession), attach `Authorization: Bearer <access_token>` to the /agent/stream fetch and to the history fetchers (and the /api/be proxy calls). Keep sending body.user_id as the anonymous fallback (BE ignores it when a token is present). No token → unchanged anonymous behavior. Refresh the token per request (getSession) so it isn't stale.</action>
  <verify>cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" npx tsc --noEmit</verify>
  <done>Logged-in requests carry the bearer token; logged-out requests behave exactly as today.</done>
</task>
```

### Task 4.1 — End-to-end verification

```xml
<task id="4.1" wave="4">
  <files>apps/api/tests/api/agent/test_identity_hybrid.py</files>
  <action>Integration assertions (extend 1.1's test or add cases): (a) anonymous turn → free, works; (b) authed turn (fake/verified token) → uses sub, creates users row; (c) after set_tier premium, the authed user bypasses quota + can reach booking; (d) forged body.user_id ignored under a valid token. Browser smoke (manual/Node24) optional: log in, confirm premium unlocks.</action>
  <verify>cd apps/api && DATABASE_URL="sqlite:///test_run.db" ../../.venv/bin/python -m pytest tests/api/agent -x; rm -f apps/api/test_run.db</verify>
  <done>Hybrid identity + tier verified across anonymous/free/premium.</done>
</task>
```

## 6. Risks / hard gates

- **Auth/authz hard gate** — adding identity-bearing auth to the agent + an admin tier endpoint.
  Confirm the JWT verification (auth.py) is production-correct (issuer/audience/JWKS). Security
  review recommended. Commits may need `RISK_WARN_CATEGORIES="auth authorization"`.
- **Don't break anonymous UX** — hybrid must fail-open to free when no token; test both paths.
- **Token handling** — never log tokens; refresh via getSession to avoid stale/expired tokens.
- **Admin role source** — relies on a `role` (or `app_metadata.role`) claim in the Supabase JWT;
  confirm how admin is marked in Supabase before 2.2.

## 7. Waves

| Wave | Tasks | Parallel | Notes |
|------|-------|----------|-------|
| 1 | 1.1 | single | hybrid identity (foundational) |
| 2 | 2.1, 2.2 | 2 (disjoint) | CLI + admin endpoint |
| 3 | 3.1 | single | FE bearer token |
| 4 | 4.1 | single | e2e verification |

## 8. Status Log

- 2026-06-28 — Drafted after discovering the agent uses an anonymous UUID, not the Supabase id,
  making `runtime-context-config` tier inert. Decisions: hybrid auth, BE-owned tier via CLU+admin
  endpoint. Lands on `feat/agent-mode-tier` so PR #43 only merges once tier is functional.
