---
slug: proxy-auth-failure-boundary
status: shipped
owner: Minh Tran
created: 2026-09-08
---

# An auth outage must not take the whole site

## 1. Motivation

Three files each non-null-asserted the same two Supabase variables and nothing validated them
anywhere, so a misconfigured deploy failed at whichever client happened to be constructed first,
with a message that said what was wrong but not that it could only be fixed by rebuilding.

**Scope reduced on 2026-09-08 (ESCALATIONS E001, decision B).** This plan originally also added a
failure boundary in `src/proxy.ts` and a startup validation hook. Six blind correctness angles
established that the outage it guarded against does not throw — `auth-js` returns its own errors and
`updateSession` discards them — that the boundary dropped session cookies `getClaims()` may already
have rotated, and that for a present-but-invalid URL it converted a loud 500 into a silently broken
site. Both were reverted. What remains is the part that was independently confirmed.

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
- Gates use `grep -q` (0 = found), never `grep -L`/`-l` exit codes: those differ between this
  machine's interactive `grep` wrapper and the `/usr/bin/grep` a script resolves, so the same
  command means different things depending on who runs it.
- Stage and commit as separate commands. No `Co-Authored-By: Claude` trailers.

## 3. Success Criteria

One test file per row. A single filter naming a missing file exits 1; a directory or multi-file
filter exits 0 on a partial match, and `-t` exits 0 when it matches nothing.

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | `requireSupabaseEnv()` returns both values when set and throws naming the absent variable when either is missing; `env.ts` reads both variables through literal `process.env.NAME` access | `cd apps/web && pnpm exec vitest run src/lib/env.test.ts` | exit 0 |
| SC-2 | Every Supabase client is constructed through the env contract | `grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/middleware.ts && grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/server.ts && grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/client.ts` | exit 0 |
| SC-3 | The workspace type-checks with the three call sites rewired | `cd apps/web && pnpm exec tsc --noEmit` | exit 0 |
| SC-4 | No bare non-null assertion on either Supabase variable survives under `lib/supabase/` | `! grep -rq "NEXT_PUBLIC_SUPABASE_URL!" apps/web/src/lib/supabase/` | exit 0 |

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
  Include a source-text gate in the same file, written as a **positive** assertion: `env.ts` must
  contain both literal strings `process.env.NEXT_PUBLIC_SUPABASE_URL` and
  `process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. Keep a negative `process.env[` check as a
  cheap extra, but the positive one is what makes the gate defeat-proof: the Next docs name **two**
  non-inlined forms, and a negative gate for one of them still passes
  `const { NEXT_PUBLIC_SUPABASE_URL } = process.env`, which ships `undefined` to the browser just
  the same. Requiring the literal text covers every variant at once.
  This is a source-text assertion on purpose — jsdom performs no inlining, so no runtime test can
  observe the defect it prevents.
  **Test mechanics you will otherwise lose time on:** the module reads both variables at module
  scope, so `vi.stubEnv` after import has no effect. Each missing-variable case needs
  `vi.resetModules()` plus a dynamic `await import("./env")`, and `src/test/setup.ts` sets both
  variables for every test file, so the case must delete them explicitly first.
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
- **Verify:** `grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/middleware.ts && grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/server.ts && grep -q "requireSupabaseEnv" apps/web/src/lib/supabase/client.ts && ! grep -rq "NEXT_PUBLIC_SUPABASE_URL!" apps/web/src/lib/supabase/`
- **Done:** All three files call `requireSupabaseEnv()`; no `NEXT_PUBLIC_SUPABASE` non-null assertion remains under `apps/web/src/lib/supabase/`; `isProtected` is exported; `PROTECTED_PREFIXES` membership is byte-identical. The checks use `grep -q`, not `grep -rL`. Measured on this machine: `-L`'s exit code differs between the interactive shell's `grep` wrapper function and the `/usr/bin/grep` that `subprocess(shell=True)` resolves — the same command returned 1 in one and 0 in the other, so a `-L`-based gate means different things depending on who runs it. `-q` is 0-on-match everywhere.
- **Criteria:** SC-2, SC-3, SC-4
- **Interfaces:** Consumes `apps/web/src/lib/env.ts`. Produces the rewired `apps/web/src/lib/supabase/middleware.ts` with an exported `isProtected`.



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

- 2026-09-08 — scope reduced to the env contract per ESCALATIONS E001 decision B; tasks 2.2 and 3.1
  and their criteria removed after six correctness angles falsified the premise they rested on.
  Remaining suite 48 files / 260 tests, tsc/lint/build clean.

- 2026-09-08 — Plan written. Intake `high-risk` / confidence raised to `high` after the user
  resolved both forks: scope covers the env contract as well as the proxy boundary, and an outage
  fails closed to the login page.
