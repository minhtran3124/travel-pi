# proxy-auth-failure-boundary — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.

---

## E001 — STOP: the branch rests on a wrong premise and one change makes a real failure worse

- raised_by: correctness-review (6 blind angles), all findings re-verified by the controller against installed sources
- date: 2026-09-08
- trigger: hard-gate (auth/session) + system-redefinition
- question: This branch should not merge as built. Which way forward?

### What was verified, and how

Every claim below was checked by reading the installed packages, not inferred.

**F1 — P1. The boundary drops session cookies that were already rotated.** Four angles found this
independently. `getClaims()` calls `getSession()` **first** (`GoTrueClient.js`, `getClaims` line 5
of the function); a refresh there writes the rotated `sb-*-auth-token` through `setAll()` onto
`updateSession`'s local `supabaseResponse` (`lib/supabase/middleware.ts:39-47`). Only *after* that
does it reach `fetchJwk` / `crypto.subtle.importKey` / `crypto.subtle.verify` (same function, lines
27, 46, 50), whose `DOMException` is **not** an `AuthError` and therefore escapes. `proxy.ts`'s
catch then builds a fresh response with no access to `supabaseResponse`, so no `Set-Cookie` reaches
the browser while Supabase has already invalidated the old refresh token — a transient error becomes
a **permanent, silent sign-out**. On the `NextResponse.next({ request })` branch it is worse: `setAll`
mutated `request.cookies`, so the render sees the new cookies and the browser does not.
This is the exact failure `lib/supabase/middleware.ts:80-91` warns about, that its own redirect path
guards at `:74-76`, and that `docs/solutions/web/nextjs-16-proxy-and-loading-boundaries.md` records —
a document written hours earlier in this same session. The test cannot catch it: the mock throws
*before* calling `setAll` (`proxy.test.ts:46-48`), so the rotate-then-fail ordering is untested by
construction.

**F2 — P1. The outage this spec was written for does not throw.** `auth-js` catches its own errors:
`catch (error) { if (isAuthError(error)) return this._returnResult({ data: null, error }); throw error }`.
`AuthRetryableFetchError` (a network failure) extends `CustomAuthError` extends `AuthError`, so an
unreachable auth host is **returned, not thrown**. `middleware.ts:58` destructures `{ data }` only
and discards `error`, so `!data?.claims` is true and a signed-in user is redirected to `/auth/login`
— the app tells them they are signed out when in fact it is broken. The new `try/catch` never runs on
this path. What it actually catches is the narrow residue: a missing env var, a `crypto.subtle`
failure, non-`AuthError` bugs.

**F3 — P1. The change makes a real misconfiguration worse.** `requireSupabaseEnv()` tests truthiness
only (`env.ts:11,17`). A present-but-invalid URL — a pasted connection string, a stripped scheme, a
placeholder — passes it, so `register()` passes and the server boots clean. `createServerClient` then
throws a plain `Error` per request (`supabase-js` validates the URL shape). **Before this branch that
was a loud 500.** After it, the catch swallows it: every user is 307'd to `/auth/login` forever, login
included, while the site looks healthy apart from one log line per request.

**F4 — P2, narrowed after a sixth angle corrected an earlier draft of this escalation.**
`register()` is **not** useless: traced through `next/dist/server/next-server.js:553-556` →
`instrumentation-globals.external.js:47,67`, a throw from `register()` **rethrows** and `prepare()`
rejects, so the Node server genuinely fails to boot. What it cannot do is the thing `design.md` §3.2
claimed — catch an image *built* with the variables and *promoted* to an environment without them.
`NEXT_PUBLIC_*` is inlined into the **server** bundle as well as the client one
(`next/dist/build/define-env.js:53` computes `getNextPublicEnvironmentVariables()` outside any
`isClient` branch; `next/dist/lib/inline-static-env.js:27` rewrites `distDir/server`, not only
`distDir/static`), so on a promoted deploy the value is a frozen build-time constant and the check
can never fire. `instrumentation.test.ts` mutates `process.env` and therefore proves a behaviour the
production bundle does not have. An earlier draft of this escalation called the whole task a no-op;
that overstated it, and the correction is recorded rather than quietly edited away.

**F6 — P2. Nothing observes an auth outage any more.** The 500 this branch removes was itself the
signal. Verified by search: no `onRequestError` hook anywhere (the new `instrumentation.ts` does not
add one), no error-reporting SDK in `apps/web`, and no deployment probe in `.github/workflows/`.
After this change a protected path 307s and everything else returns 200, so an uptime check and a
load-balancer health probe both read the site as healthy while every user is being told they are
signed out. Whatever replaces the boundary has to leave an operator-visible signal behind.

**F5 — P2.** The outage path returns without `applyLangParam`, so `?lang=` is never applied and never
stripped; it re-fires and re-fails on every subsequent navigation. This was a deliberate design
choice ("not worth a second failure mode"), but two angles independently judged it wrong: locale
handling has no Supabase dependency, and the auth-gate redirect on the success path *does* apply it.

### What still stands

- Reading the two variables in one place with literal access, and the source-text gate that keeps
  them literal. The inlining constraint it enforces is real and independently confirmed.
- Exporting `isProtected` rather than duplicating the prefix list.
- The `next=` parity fix on the redirect.

### Options

- A) **Abandon the branch.** Close it, keep nothing. Honest, and the escalation goes back to the
  backlog with everything learned recorded. E001's original defect (a 500 on missing env) is real but
  narrower than described, and no longer urgent once F2 shows the common outage never 500s.
- B) **Reduce to the env contract only.** Keep `lib/env.ts`, the three call sites and the
  `isProtected` export; drop `instrumentation.ts` (F4) and the whole `proxy.ts` boundary (F1, F3).
  Ships a small real improvement — one error message instead of three — and removes every change
  that rests on a wrong premise. Recommended.
- C) **Redesign the boundary properly.** The boundary must live *inside* `updateSession` so it can
  reach `supabaseResponse` and carry rotated cookies; it must read `getClaims()`'s `error` to tell an
  outage from a signed-out visitor; it must distinguish configuration errors (fail loud) from
  transient ones (fail closed); and `requireSupabaseEnv` must validate URL shape, not presence. That
  is a larger, genuinely high-risk piece of auth work and deserves its own design, not a patch on
  this one.

- default_if_no_response: BLOCK
- decision: pending
- decided_by: <name once decided>
- decided_at: <YYYY-MM-DD>
