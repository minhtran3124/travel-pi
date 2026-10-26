# proxy-auth-failure-boundary — Summary

Lane: high-risk
Confidence: medium
Reason: the `auth` hard gate fires — the change is a failure-mode decision on the Supabase session-refresh path that runs in the proxy on every request. Confidence medium: the defect and its blast radius are established, but the intended failure behaviour (degrade to signed-out vs fail closed) is a product decision that has not been made.
Flags: auth, existing behavior, weak proof
Affects: apps/web/src/proxy.ts, apps/web/src/lib/supabase/middleware.ts
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

Raised by `correctness-review` (guard-completeness angle) during `review-c3-web-ssr-i18n`, and split
out by user decision on 2026-09-08 ("tach spec rieng ra"). Verbatim finding:

> `apps/web/src/proxy.ts:6` awaits `updateSession(request)` with no boundary. If
> `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` are unset in a preview or CI
> deploy — `lib/supabase/middleware.ts:29-30` non-null-asserts both, and `createServerClient` throws
> **synchronously** — or if `getClaims()` rejects on an unreachable JWKS host, the rejection escapes
> the proxy and Next returns **500 for every path the matcher covers**, including `/auth/login` and
> `/auth/callback`: the pages a user needs to recover. The `isProtected` guard correctly limits the
> auth gate to four prefixes, but it only runs on the success path; nothing bounds the failure path,
> so an auth outage takes the whole site rather than four prefixes.

Source: `specs/review-c3-web-ssr-i18n/ESCALATIONS.md` E001, decision A.

## What changed

The two Supabase environment variables now have one contract. Three files each non-null-asserted
them and nothing validated them anywhere, so a misconfigured deploy failed at whichever client
happened to be constructed first, with a message that named the problem but not the fix.
`requireSupabaseEnv()` names the absent variable and says it is required at **build** time, because
Next inlines `NEXT_PUBLIC_*` during `next build` and it cannot be supplied later.

**That is all that shipped.** The branch originally also added a failure boundary in `src/proxy.ts`
and a startup validation hook. Both were reverted — see `### Correctness Findings`.

### Rationale

The escalation described one defect; research found two wearing one coat. **Misconfiguration** is
deterministic and belongs as early as possible. **An outage** is transient and belongs at the request
boundary. Only the first survived scrutiny.

The reads use literal property access at module scope, one line per variable, with a comment saying
why and a source-text gate holding them there. Next inlines `NEXT_PUBLIC_*` by textually replacing
`process.env.NAME` and does not inline dynamic access, so the tidy version of this — a loop over a
list of names — would ship `undefined` to the browser. The gate is a positive assertion (both literal
strings present) rather than a ban on one bad form, because the docs name two and destructuring is a
third. jsdom performs no inlining, so no runtime test can see the defect.

The checks live inside `requireSupabaseEnv()` rather than at module scope, measured both ways:
importing must not throw, calling must. `lib/supabase/client.ts` is imported by browser code, and an
import-time throw there would blank every route including ones that never touch Supabase.

### Alternatives considered

- **Also add the proxy failure boundary and the startup hook** — built, then reverted. Six blind
  correctness angles falsified the premise. Recorded in full under `### Correctness Findings` and in
  `design.md` §3.2/§3.3, which are kept as rejected analysis for whoever attempts option C.
- **Validate the variables at module scope.** Rejected on measurement — see Rationale.
- **Keep the three non-null assertions and fix only the proxy.** Rejected once research found the
  same assertion in three files with nothing validating them.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Env contract behaves and reads literally | `cd apps/web && pnpm exec vitest run src/lib/env.test.ts` | 0 | 6 tests; includes the positive source-text gate | SC-1 |
| Every Supabase client goes through it | `grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/middleware.ts && grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/server.ts && grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/client.ts` | 0 | `-q`, not `-L`: `-L`'s exit code is not portable across the two greps on this machine | SC-2 |
| Workspace type-check | `cd apps/web && pnpm exec tsc --noEmit` | 0 | | SC-3 |
| No bare non-null assertion survives | `! grep -rq "NEXT_PUBLIC_SUPABASE_URL!" apps/web/src/lib/supabase/` | 0 | | SC-4 |
| Full suite | `cd apps/web && pnpm exec vitest run` | 0 | 48 files / 260 tests | |
| Build | `cd apps/web && pnpm build` | 0 | | |

### Correctness Findings

Six blind angles ran over the branch as originally built. Every finding below was re-verified by the
controller against the installed packages, not taken from the reports.

**Reverted because of these — the boundary and the startup hook:**

- **The outage this spec was written for does not throw.** `auth-js` catches its own errors and
  returns `{ data: null, error }`; `AuthRetryableFetchError` (a network failure) is an `AuthError`.
  `middleware.ts:58` discards `error`, so during an outage a signed-in user is already redirected to
  `/auth/login` — the app tells them they are signed out when it is in fact broken. The boundary
  never ran on that path.
- **The boundary dropped rotated session cookies.** `getClaims()` refreshes first, writing the new
  `sb-*` token through `setAll()` onto `updateSession`'s local response; only then does it reach the
  crypto steps whose `DOMException` escapes. A catch that builds a fresh response cannot reach that
  object, so the browser keeps a refresh token Supabase has already consumed — a transient error
  becomes a permanent silent sign-out. The test could not catch it: the mock threw *before* `setAll`.
- **It made a real misconfiguration worse.** `requireSupabaseEnv()` tests presence, not shape. A
  present-but-invalid URL passes it and `createServerClient` then throws per request. That was a
  loud 500 before the branch; with the boundary it became a healthy-looking site redirecting every
  user to a login page that could not work.
- **`register()` could not detect its stated case.** `NEXT_PUBLIC_*` is inlined into the server
  bundle too, so a promoted build carries frozen values. It does still fail the boot when the build
  itself lacked the variables — narrower than the design claimed.

**Left open, and not introduced by this branch:**

- An auth outage is silently indistinguishable from "signed out", and nothing observes it: no
  `onRequestError` hook, no error-reporting SDK, no deployment probe. Protected paths 307 and
  everything else returns 200, so an uptime check reads the site as healthy. This is the real defect
  behind E001 and it belongs to option C.
- `requireSupabaseEnv()` validates presence, not URL shape.

### Not auto-verified

- **No misconfigured deploy was exercised end to end.** The env contract is proven by unit tests and
  by a direct measurement that `createServerClient` throws synchronously on a falsy url or key. No
  one deployed with a variable removed and watched what a user sees.
- **The inlining claim is docs-plus-source-reading, not a measured browser bundle.** The positive
  source-text gate enforces the shape the docs require; no one inspected a built client chunk.
- The `NEXT_PUBLIC_*`-is-inlined-into-the-server-bundle finding rests on reading
  `next/dist/build/define-env.js` and `next/dist/lib/inline-static-env.js`, not on observing a
  promoted deploy.

### Rollback

- `git revert` the three commits that survive, or simply do not merge. Nothing here is deployed.
- Reverting `lib/env.ts` requires also reverting the commit that routes the three factories through
  it, or they import a module that no longer exists.
- No migration, no backend change, no public API change.

### Harness-Delta

- none
