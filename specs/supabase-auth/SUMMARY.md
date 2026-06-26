# supabase-auth — Summary

Lane: high-risk
Confidence: high
Reason: Auth hard gate fired (login/session/JWT) on both apps/web and apps/api; plus authorization and weak-proof flags. Scope confirmed by human (E001/E002 decided), so confidence is high while the lane stays high-risk.
Flags: Auth, Authorization, External systems, Weak proof
Affects: new auth surface in apps/web (root middleware, auth routes/pages, Supabase clients in src/lib/supabase/*) AND new JWT verification in apps/api (FastAPI). No DB migration (no profiles table this slice).
Input-type: new initiative

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- Verbatim user request at intake. -->

"implementation auth feature for user using supabase"

Session context preceding this intake (foundation already laid, not yet wired):
- Installed `@supabase/supabase-js` and `@supabase/ssr` in apps/web.
- Added `src/lib/supabase/{client,server,middleware}.ts` via the Supabase shadcn registry
  (`@supabase/supabase-client-nextjs`).
- Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in `.env.local`.
- Root `src/middleware.ts` NOT yet created — `updateSession` is not running.

## What changed

Phase 1 shipped on branch `feat/supabase-auth` (8 commits):
- **apps/web**: root `middleware.ts` refreshes the Supabase session (redirect-on-unauth
  removed — no route gating this slice); auth server actions (email+password sign-in/up,
  magic link, sign-out, deferred-guarded OAuth); `/auth/callback` (code exchange),
  `/auth/confirm` (OTP verify), error page; login + sign-up pages; sign-out button; OAuth
  buttons rendered disabled (deferred).
- **apps/api**: `app/core/auth.py` `get_current_user` verifies Supabase access tokens via the
  project JWKS endpoint (RS256/ES256) → `AuthUser` or `AuthError` (401); Supabase settings +
  derived JWKS/issuer; `AuthError` domain exception; `pyjwt`+`cryptography` deps. Not yet
  attached to existing routers (contained blast radius). 9 offline unit tests.

Deferred per scope: OAuth (needs Supabase dashboard provider config); route protection;
profiles table. Backend auth is built+tested but the API's Supabase env is not yet configured.

### Rationale

Auth is a hard gate under `rules/auto-correct-scope.md` Rule 4; the request is broad enough that
two engineers would build materially different things, so a human must narrow scope before a plan.

### Alternatives considered

- python-jose vs PyJWT for JWKS verification → chose **PyJWT** (`PyJWKClient`): better
  maintained, built-in key caching, already aligns with the cryptography backend.
- Gate routes in middleware now vs later → **later** (scope: no protection this slice).

### Deviations

- Rule 1 — Removed the generated redirect-to-`/auth/login` block from `updateSession`
  (`apps/web/src/lib/supabase/middleware.ts`); it gated the whole app, contradicting the
  confirmed "no route protection" scope. Commit `970d030`.
- Rule 3 — Added `pyjwt` + `cryptography` to `apps/api/requirements.txt` (needed for JWKS
  verification). Commit `2d36d7d`.
- Rule 3 — Relaxed the `cryptography` cap to `<50` after an initial `<46` wrongly downgraded
  the already-installed 49.0.0; restored to 49.0.0.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Web typecheck | `cd apps/web && pnpm exec tsc --noEmit` | 0 | clean |
| Web prod build | `cd apps/web && pnpm build` | 0 | all 5 /auth routes + middleware registered |
| API auth tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/auth -q` | 0 | 9 passed (offline, monkeypatched JWKS) |
| API lint | `cd apps/api && ../../.venv/bin/ruff check app/core/auth.py app/core/config.py app/exceptions.py` | 0 | clean |
| Full API suite (zero-config, `.env` aside) | `mv apps/api/.env aside; pytest …; restore` | 0 | previously-failing 14 are env-only (`OPENAI_API_KEY=test` in dev `.env`), green without it |

### Rollback

- Revert the feature branch commits: `git revert 199a272 39bd73a 5d02b0b 2d36d7d 970d030`
  (and `872dedc` for the spec docs), or delete the branch `feat/supabase-auth`.
- Uninstall added deps: `uv pip uninstall pyjwt cryptography` (cryptography is also a
  transitive dep elsewhere — leave it).

### Harness-Delta

- none
