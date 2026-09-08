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

An auth failure no longer takes the whole site down. `proxy.ts` awaited the Supabase session
refresh with no boundary, so an unreachable auth host or a missing environment variable returned
500 for **every** matched path — including `/auth/login` and `/auth/callback`, the pages a user
needs in order to recover. The blast radius of an auth outage was the entire site rather than the
four protected prefixes the gate actually covers.

It now fails closed: a protected path redirects to the login page as though the visitor were signed
out, carrying the `next` return path exactly as the normal gate does; everything else renders.
Signing in will not work while the backend is down, but the user reaches a page that renders and a
state they can read.

Separately, the two Supabase environment variables now have one contract. Three files each
non-null-asserted them and nothing validated them anywhere, so a misconfigured deploy failed at
whichever client happened to be constructed first. `requireSupabaseEnv()` names the absent variable
and says it is required at build time, and `register()` fails the server at startup rather than on
every user request.

### Rationale

The escalation described one defect; research found two wearing one coat, and they want different
fixes. **Misconfiguration** is deterministic and belongs as early as possible — at build, or at
server start. **An outage** is transient and belongs at the request boundary. Conflating them is why
"what should happen?" read as one question when it was two.

Two facts were measured rather than assumed, and both shaped the result:

- `createServerClient` throws **synchronously** on a missing url or key — run against the installed
  package. So Supabase's message was never the problem; where it surfaced was.
- `NEXT_PUBLIC_*` variables are inlined at build by textual replacement of `process.env.NAME`, and
  the Next docs state that dynamic access is **not** inlined. The natural shape for a validator — a
  loop over a list of variable names — would therefore ship `undefined` to the browser and cause the
  very outage this spec removes. `env.ts` reads each name literally and a source-text gate holds it
  there, because jsdom performs no inlining and no runtime test can see the defect.

The checks live inside `requireSupabaseEnv()` rather than at module scope, measured both ways:
importing must not throw, calling must. `lib/supabase/client.ts` is imported by browser code, and an
import-time throw there would blank every route including ones that never touch Supabase.

The `try` covers `updateSession` alone. `applyLangParam` sits after it, so a throw from there escapes
instead of being logged under the wrong function's name and failing a request closed during an
incident that is not an auth incident.

### Alternatives considered

- **Fail open — render the page during an outage.** Rejected: it looks signed-in but every API call
  401s, and widening an auth gate while the auth backend is unstable is the wrong direction.
- **A dedicated "auth unavailable" page.** Rejected for now: a new route plus catalog entries in two
  languages for a state that should be rare. `/auth/login` already exists, already renders, and
  already explains itself. Revisit if outages prove common.
- **Fix only the proxy boundary, as the escalation described.** Rejected once research found the same
  assertion in three files with nothing validating them: the proxy would stop returning 500 while a
  missing variable still broke the browser client and the route handlers separately.
- **Validate env at module scope.** Rejected on measurement — see Rationale.
- **Re-list the protected prefixes in the failure path.** Rejected: two definitions drift, and the
  outage path would then protect a different set of routes than the success path.

### Deviations

- none

### Verify

Every row re-run on the branch head; each is a single pipe-free command naming the criterion it
satisfies. The 6 SC rows live in `PLAN.md` §3.

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Env contract behaves and reads literally | `cd apps/web && pnpm exec vitest run src/lib/env.test.ts` | 0 | 6 tests; includes the positive source-text gate | SC-1 |
| Every Supabase client goes through it | `grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/middleware.ts && grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/server.ts && grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/client.ts` | 0 | `-q`, not `-L`: `-L`'s exit code is not portable across the two greps on this machine | SC-2 |
| Startup validation actually validates | `cd apps/web && pnpm exec vitest run src/instrumentation.test.ts` | 0 | 3 tests; asserts `register()` throws, not that a symbol exists | SC-3 |
| Outage fails closed, and the success path is unmoved | `cd apps/web && pnpm exec vitest run src/proxy.test.ts` | 0 | 9 tests; the five pre-existing branch cases are byte-identical | SC-4 |
| Workspace type-check | `cd apps/web && pnpm exec tsc --noEmit` | 0 | | SC-5 |
| No bare non-null assertion survives | `! grep -rq "NEXT_PUBLIC_SUPABASE_URL!" apps/web/src/lib/supabase/` | 0 | | SC-6 |
| Full suite | `cd apps/web && pnpm exec vitest run` | 0 | 49 files / 267 tests, from 47 / 254 at the branch point | |
| Build | `cd apps/web && pnpm build` | 0 | route table still lists `f Proxy (Middleware)` | |

### Not auto-verified

- **No auth outage was simulated against a running deployment.** The outage path is proven by unit
  tests that force `getClaims()` to reject through the `@supabase/ssr` mock — reached **provenance**,
  not **truth**. Nobody took Supabase away from a live instance and watched `/auth/login` render.
- **`register()` was not observed running under `next build` / `next start`.** The test invokes it
  directly. That it is wired as Next's startup hook rests on the file convention, which `pnpm build`
  exercises only indirectly.
- **The inlining claim is docs-plus-reasoning, not a measured browser bundle.** The positive
  source-text gate enforces the shape the docs require; no one inspected a built client chunk to
  confirm the values were inlined.
- A Rule-3 test-only `console.error` spy works around an upstream Next 16.2.9 / Node 24
  `AsyncLocalStorage` invariant. An independent reviewer removed the spy and reproduced the exact
  upstream error, so it is an environment artifact rather than a defect here — but the workaround
  itself is untested against a future Next release.

### Rollback

- Whole branch: do not merge, or `git revert --no-commit <base>..HEAD && git commit`.
- The boundary alone: `git revert 29a656e`. Reverting the env contract (`d562ced`) requires also
  reverting `82c0651`, which routes the three factories through it, or they will import a module
  that no longer exists.
- No migration, no backend change, no public API change.

### Harness-Delta

- none
