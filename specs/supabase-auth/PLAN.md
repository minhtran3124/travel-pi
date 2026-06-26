---
slug: supabase-auth
status: shipped
owner: Minh Tran
created: 2026-06-26
---

# Supabase Auth — user sign-in (web) + JWT verification (api)

## 1. Motivation

Add a user-authentication surface using Supabase. Phase 1 ships **email+password** and
**magic link** sign-in in `apps/web` (Next.js App Router) plus **Supabase-JWT verification**
in `apps/api` (FastAPI) via the project's JWKS endpoint. Foundation already in place:
`@supabase/supabase-js` + `@supabase/ssr` installed, `src/lib/supabase/{client,server,middleware}.ts`
generated, env vars set in `.env.local`.

## 2. Non-goals (this slice)

- **No route protection** — build login/logout + session plumbing only; gating `/trips/*`
  comes later. (Confirmed in SUMMARY/ESCALATIONS.)
- **No profiles table / RLS** — rely on Supabase `auth.users`.
- **OAuth (Google/GitHub) is scaffolded but DEFERRED** — UI + action wired, flagged disabled,
  blocked on Supabase dashboard provider config the user will do later. Do not claim OAuth works.
- No changes to existing trip/expense/budget endpoint behavior (no `Depends(get_current_user)`
  added to existing routers yet — the dependency is built + tested in isolation).

## 3. Success Criteria

- A user can sign up with email+password, sign in, and sign out in `apps/web`; session persists
  across requests via root middleware (`updateSession`).
- A user can request a magic link and complete sign-in via `/auth/confirm`.
- `apps/api` exposes a reusable `get_current_user` dependency that verifies a Supabase access
  token against the JWKS endpoint (RS256/ES256), returns the user on success, raises 401 on
  missing/invalid/expired token. Covered by unit tests using a locally-signed test key.
- OAuth buttons render but are visibly disabled with a "configure provider" note.
- `make test` (api) green; `pnpm build` (web) green.

## 4. Tasks

### Task 1.1 — Web: wire root middleware (session refresh)

```xml
<task id="1.1" wave="1">
  <files>apps/web/src/middleware.ts</files>
  <action>Create root middleware calling updateSession from @/lib/supabase/middleware. Add config.matcher excluding _next/static, _next/image, favicon, and common image extensions. This is what keeps the Supabase session fresh on every request. Do NOT add redirect-on-unauthenticated logic (no route protection this slice).</action>
  <verify>cd apps/web && pnpm exec tsc --noEmit</verify>
  <done>middleware.ts compiles; updateSession invoked; no route gating.</done>
</task>
```

### Task 1.2 — API: Supabase config + JWKS auth dependency + AuthError

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/core/config.py, apps/api/app/core/auth.py, apps/api/app/exceptions.py, apps/api/requirements.txt</files>
  <action>requirements.txt: add `pyjwt>=2.8.0` and `cryptography>=42.0.0`. config.py: add settings supabase_project_ref, supabase_jwks_url (default derived from ref: https://<ref>.supabase.co/auth/v1/.well-known/jwks.json), supabase_jwt_issuer, supabase_jwt_audience="authenticated", supabase_auth_enabled (default False so existing tests/dev are unaffected). exceptions.py: add AuthError(AppError) mapping to 401 (follow existing AppError subclass pattern; confirm errors.py already maps 401→"Unauthorized"). auth.py: implement get_current_user(request) -> AuthUser using jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token) then jwt.decode(..., algorithms=["RS256","ES256"], issuer=..., audience=...). Extract Bearer token from Authorization header; raise AuthError on missing/invalid/expired. Cache the PyJWKClient at module scope (it caches keys internally). Define a small AuthUser dataclass/Pydantic model (id=sub, email, role). Export CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]. Module-scoped logger; never log the token.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "import jwt, cryptography; from app.core import auth, config; print('ok')"</verify>
  <done>Imports resolve; get_current_user + CurrentUserDep + AuthError defined; new deps installed.</done>
</task>
```

### Task 2.1 — Web: auth server actions + callback/confirm/error routes

```xml
<task id="2.1" wave="2">
  <files>apps/web/src/app/auth/actions.ts, apps/web/src/app/auth/callback/route.ts, apps/web/src/app/auth/confirm/route.ts, apps/web/src/app/auth/auth-code-error/page.tsx</files>
  <action>actions.ts ('use server'): signInWithPassword, signUpWithPassword, signInWithMagicLink (supabase.auth.signInWithOtp with emailRedirectTo=/auth/confirm), signOut (revalidate + redirect). Add signInWithOAuth(provider) but guard it to throw/return a "provider not configured" result — DEFERRED. Use createClient() from @/lib/supabase/server. callback/route.ts: GET handler, exchangeCodeForSession(code) for PKCE/OAuth, redirect to next or '/'. confirm/route.ts: GET handler reading token_hash+type, supabase.auth.verifyOtp({type, token_hash}), redirect on success else to /auth/auth-code-error. auth-code-error/page.tsx: minimal error page using existing design tokens (ink/lime), no shadcn token injection.</action>
  <verify>cd apps/web && pnpm exec tsc --noEmit</verify>
  <done>All four files compile; actions cover email+password, magic link, signOut; OAuth deferred-guarded; routes handle code + token_hash.</done>
</task>
```

### Task 2.2 — API: unit tests for the JWKS auth dependency

```xml
<task id="2.2" wave="2">
  <files>apps/api/tests/api/auth/test_jwt_auth.py, apps/api/tests/api/auth/conftest.py</files>
  <action>Generate an RSA keypair in-test; build a fake JWKS and monkeypatch the PyJWKClient (or inject the public key) so no network is hit. Sign tokens locally. Cases: valid token → AuthUser with sub/email; missing Authorization header → 401; malformed/garbage token → 401; expired token → 401; wrong audience/issuer → 401. Mount a tiny throwaway route using CurrentUserDep on a test app (or call get_current_user directly with a fabricated Request). Follow the existing tests/conftest dependency-override pattern; do not hit the real Supabase JWKS URL.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/auth/test_jwt_auth.py -x</verify>
  <done>All auth cases pass offline; no network; 401 on every invalid path, 200/user on valid.</done>
</task>
```

### Task 3.1 — Web: login + sign-up pages + sign-out control

```xml
<task id="3.1" wave="3">
  <files>apps/web/src/app/auth/login/page.tsx, apps/web/src/app/auth/sign-up/page.tsx, apps/web/src/components/auth/SignOutButton.tsx, apps/web/src/components/auth/OAuthButtons.tsx</files>
  <action>login/page.tsx: email+password form (calls signInWithPassword), a "send magic link" affordance (signInWithMagicLink), link to sign-up. sign-up/page.tsx: email+password+confirm form (signUpWithPassword). SignOutButton.tsx: client component calling signOut action. OAuthButtons.tsx: Google + GitHub buttons rendered DISABLED with a small "configure in Supabase dashboard" hint (DEFERRED). Use the project's existing design tokens/components (warm light theme: ink primary, lime accent, Meter/panel styles) — do NOT introduce shadcn CSS-variable tokens into globals.css. Match existing component conventions in src/components.</action>
  <verify>cd apps/web && pnpm exec tsc --noEmit && pnpm build</verify>
  <done>Pages build; forms wired to actions; OAuth visibly disabled; styling consistent with existing design system.</done>
</task>
```

## 5. Risks

- **External provider config (hard dependency):** magic link + OAuth need redirect URLs in the
  Supabase dashboard allow-list (`/auth/confirm`, `/auth/callback`). Magic link won't deliver a
  working link until the redirect URL is allow-listed. Flag to user before acceptance testing.
- **API auth is a backend contract change:** `CLAUDE.md` states the API has no auth. We add the
  dependency but do NOT attach it to existing routers this slice — keeps blast radius contained.
- **JWKS network at runtime:** `PyJWKClient` fetches keys from Supabase on first use; tests must
  monkeypatch it (Task 2.2) to stay offline and deterministic.
- **Design-system regression:** auth UI must reuse existing tokens; a `shadcn add` of UI
  components could inject conflicting `:root`/`.dark` blocks into globals.css — avoid.
- **Algorithm set:** confirm whether the project signs RS256 vs ES256; include both in `algorithms`.

## 6. Status Log

- 2026-06-26 — Intake: high-risk (Auth hard gate ×2: web + api), confidence high after scope
  confirmation. Plan drafted, visual-reviewed.
- 2026-06-26 — Executed all 3 waves on `feat/supabase-auth`. ✓ Task 1.1 `970d030`, 1.2
  `2d36d7d`, 2.1 `5d02b0b`, 2.2 `39bd73a`, 3.1 `199a272` (+ spec `872dedc`). Verify: web
  tsc+build green; api auth tests 9/9; full suite green minus pre-existing `.env`
  OPENAI_API_KEY=test failures. Status: shipped (Phase 1), OAuth deferred.
