---
slug: proxy-auth-failure-boundary
status: proposed
owner: Minh Tran
created: 2026-09-08
---

# An auth outage must not take the whole site

## 1. Motivation

`src/proxy.ts` awaits the Supabase session refresh with no boundary, so a missing env var or an
unreachable auth host returns 500 for every matched path — including `/auth/login`, the page a user
needs to recover. Raised as E001 by the correctness review of `review-c3-web-ssr-i18n` and split out
by user decision. The defect predates that branch.

## 2. Non-goals

- No retry, backoff, health probe, or claim caching.
- No change to what `updateSession` does on the success path.
- No new error page: `/auth/login` already exists and renders.
- No change to `PROTECTED_PREFIXES` membership — it is exported for reuse, not edited.

## Global Constraints

- Node 24 for every FE command: `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`.
- Checks are written to run from the **repository root**; rows needing the workspace begin
  `cd apps/web && …`.
- **`src/lib/env.ts` must read each variable with literal property access**
  (`process.env.NEXT_PUBLIC_SUPABASE_URL`). Next inlines `NEXT_PUBLIC_*` at build time and
  explicitly does **not** inline dynamic lookups, so `process.env[name]` in a loop ships `undefined`
  to the browser and creates the very outage this spec removes.
- The failure path must import `isProtected`, never re-list the prefixes. Two copies will drift and
  the outage path would then protect a different route set than the success path.
- This branch is stacked on `feat/review-c3-web-ssr-i18n`; its PR targets that branch, not `main`.
- Stage and commit as separate commands. No `Co-Authored-By: Claude` trailers.

## 3. Success Criteria

One test file per row. A single filter naming a missing file exits 1; a directory or multi-file
filter exits 0 on a partial match, and `-t` exits 0 when it matches nothing.

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | `requireSupabaseEnv()` returns both values when set and throws naming the absent variable when either is missing; `env.ts` contains no dynamic `process.env[...]` access | `cd apps/web && pnpm exec vitest run src/lib/env.test.ts` | exit 0 |
| SC-2 | No Supabase client is constructed from a bare non-null assertion any more | `grep -rL "requireSupabaseEnv" apps/web/src/lib/supabase/middleware.ts apps/web/src/lib/supabase/server.ts apps/web/src/lib/supabase/client.ts` | exit 1 — every file matches, so none is listed |
| SC-3 | The server validates the Supabase env once at startup | `grep -q "export function register" apps/web/src/instrumentation.ts && grep -q "requireSupabaseEnv" apps/web/src/instrumentation.ts` | exit 0 |
| SC-4 | During an auth outage a protected path redirects to the login page and an unprotected path still renders; no path throws | `cd apps/web && pnpm exec vitest run src/proxy.test.ts` | exit 0 |
| SC-5 | The workspace type-checks with the three call sites rewired | `cd apps/web && pnpm exec tsc --noEmit` | exit 0 |

## 4. Tasks

### Task 1.1 — The env contract (wave 1)

- **Files:** apps/web/src/lib/env.ts, apps/web/src/lib/env.test.ts
- **Action:** Write the tests first, then the module.
  Export `requireSupabaseEnv(): { url: string; key: string }`. Read the two variables with
  **literal** property access at module scope — `process.env.NEXT_PUBLIC_SUPABASE_URL` and
  `process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. Throw one error naming the variable that is
  absent and stating it is required at **build** time, since `NEXT_PUBLIC_*` is inlined by
  `next build` and cannot be supplied later.
  Add a comment above the reads explaining why a loop is forbidden here; the next reader will
  otherwise "tidy" it into one.
  Include the grep gate as a test in the same file: `env.ts` must contain no `process.env[`
  occurrence. This is a source-text assertion on purpose — jsdom performs no inlining, so no runtime
  test can observe the defect it prevents.
- **Verify:** `cd apps/web && pnpm exec vitest run src/lib/env.test.ts`
- **Done:** Both values returned when set; each missing variable produces an error whose message contains that variable's name; the gate test fails if `process.env[` is introduced into `env.ts`.
- **Criteria:** SC-1
- **Interfaces:** Consumes the two NEXT_PUBLIC Supabase variables. Produces `apps/web/src/lib/env.ts`, `apps/web/src/lib/env.test.ts`.

### Task 2.1 — Route the three Supabase factories through it (wave 2)

- **Files:** apps/web/src/lib/supabase/middleware.ts, apps/web/src/lib/supabase/server.ts, apps/web/src/lib/supabase/client.ts
- **Action:** Replace `process.env.NEXT_PUBLIC_SUPABASE_URL!` / `…PUBLISHABLE_KEY!` in all three
  with `requireSupabaseEnv()`. Behaviour on a correct configuration is unchanged; only the failure
  message and its origin change.
  In `middleware.ts`, also export `isProtected` — task 3.1 needs it and must not re-list the
  prefixes. Do not change the prefix list, and do not otherwise touch `updateSession`: the warning
  block about running code between `createServerClient` and `getClaims()` still governs this file.
- **Verify:** `grep -rL "requireSupabaseEnv" apps/web/src/lib/supabase/middleware.ts apps/web/src/lib/supabase/server.ts apps/web/src/lib/supabase/client.ts`
- **Done:** All three files call `requireSupabaseEnv()`; no `NEXT_PUBLIC_SUPABASE` non-null assertion remains under `apps/web/src/lib/supabase/`; `isProtected` is exported; `PROTECTED_PREFIXES` membership is byte-identical.
- **Criteria:** SC-2, SC-5
- **Interfaces:** Consumes `apps/web/src/lib/env.ts`. Produces the rewired `apps/web/src/lib/supabase/middleware.ts` with an exported `isProtected`.

### Task 2.2 — Validate at server startup (wave 2)

- **Files:** apps/web/src/instrumentation.ts
- **Action:** Add the Next instrumentation file with an exported `register()` that calls
  `requireSupabaseEnv()`. Next runs `register` once on server startup, so a deploy built or promoted
  without the variables fails loudly at boot instead of returning 500 on every user request.
  Note in a comment what this cannot do: a **client** bundle built without the variables already has
  `undefined` inlined and nothing at runtime can recover it — this guards the server half only.
- **Verify:** `grep -q "export function register" apps/web/src/instrumentation.ts && grep -q "requireSupabaseEnv" apps/web/src/instrumentation.ts`
- **Done:** `src/instrumentation.ts` exports `register` and calls `requireSupabaseEnv()`; the comment states the client-bundle limit.
- **Criteria:** SC-3
- **Interfaces:** Consumes `apps/web/src/lib/env.ts`. Produces `apps/web/src/instrumentation.ts`.

### Task 3.1 — The outage boundary (wave 3)

- **Files:** apps/web/src/proxy.ts, apps/web/src/proxy.test.ts
- **Action:** Wrap the `updateSession` call in `try/catch`. On success the existing composition is
  unchanged. On a throw, return the fail-closed response: a 307 to `/auth/login` when
  `isProtected(request.nextUrl.pathname)`, otherwise `NextResponse.next({ request })`. Import
  `isProtected` from `lib/supabase/middleware` — do not re-list the prefixes.
  Log once with `console.error` including the pathname.
  Skip `applyLangParam` entirely on the failure path: a locale preference is not worth a second
  failure mode during an outage.
  The handler must read only `request.nextUrl.pathname` and perform no I/O, so the boundary cannot
  itself throw.
  Extend `src/proxy.test.ts` with outage cases; keep all five existing branch cases passing
  unchanged — they are the proof the success path did not move.
- **Verify:** `cd apps/web && pnpm exec vitest run src/proxy.test.ts`
- **Done:** With `updateSession` mocked to reject, a request to `/trips` returns 307 to `/auth/login` and a request to `/` returns a non-redirect response; neither throws. The five pre-existing success-path cases still pass. A grep in the test asserts `proxy.ts` imports `isProtected` rather than containing the string `'/bookings'`.
- **Criteria:** SC-4, SC-5
- **Interfaces:** Consumes the exported `isProtected` from `apps/web/src/lib/supabase/middleware.ts`. Produces the guarded `apps/web/src/proxy.ts`.

## 5. Risks

- **The inlining trap.** A validator written as a loop over variable names ships `undefined` to the
  browser and reproduces the outage. Guarded by a source-text gate in Task 1.1, because no runtime
  test can see it.
- **A duplicated prefix list.** If task 3.1 re-lists the protected routes, the failure path and the
  success path will drift apart silently. Guarded by a grep in the Task 3.1 tests.
- **Touching the session-refresh path.** `updateSession` itself is not modified; only its caller is
  wrapped. The in-file warning about `createServerClient` / `getClaims()` ordering still holds.
- **Stacked branch.** Based on `feat/review-c3-web-ssr-i18n`, which is unmerged. If that branch
  changes during review, rebase before opening the PR.

## 6. Checks that deliberately sit outside the SC table

- `cd apps/web && pnpm build` — the only check that proves Next still resolves `src/proxy.ts` and
  picks up `src/instrumentation.ts`. Too slow for an SC row; run before opening the PR.
- `cd apps/web && pnpm exec vitest run` — the full suite (47 files / 254 tests at branch point) runs
  at wave boundaries and before the PR, never as an SC row.

## 7. Status Log

- 2026-09-08 — Plan written. Intake `high-risk` / confidence raised to `high` after the user
  resolved both forks: scope covers the env contract as well as the proxy boundary, and an outage
  fails closed to the login page.
