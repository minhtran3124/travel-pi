# review-c1-e2e-auth-ci — Research Brief

Depth: **Deep** (intake lane `high-risk` → Deep per `rules/research-depth.md`; not upgraded or
downgraded during research). External surface: **yes** — a new devDependency (`@next/env`), a
version-specific Playwright API (setup projects / `storageState`), and an external system
(Supabase Auth) reached over the network from CI. So official docs were required, not optional.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **use built-in** — Playwright's own setup-project + `storageState` pattern, plus `@next/env`'s `loadEnvConfig`, both used exactly as their official docs prescribe. |
| **Why this is the lightest credible path** | Every capability the design needs already ships in the two dependencies the repo has (Playwright 1.61.1 installed, `@next/env` 16.2.9 already in the pnpm store as a transitive of `next`); nothing has to be written but glue. |
| **Confidence** | 90% |
| **Next step** | `writing-plans` → `PLAN.md` for the seven files in the design's Components list; the human prerequisites (Supabase e2e user + 4 GitHub secrets) must be done before the CI task can be verified. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo (pnpm workspaces + Turborepo): FastAPI `apps/api`, Next.js `apps/web` |
| Primary language + runtime | TypeScript on Node 24 (`engines.node >=22.13`); Python 3.12 in CI / 3.14 locally for the BE |
| Frameworks / platforms | Next.js 16.2.9 (App Router, next-intl, next-themes), React 19.2.4, Playwright 1.61.1, FastAPI + SQLAlchemy, Supabase Auth (`@supabase/ssr` 0.12) |
| Relevant packages | `@playwright/test` (`^1.49`, resolved 1.61.1), `next` 16.2.9, `@supabase/ssr`, `vitest` 2.1 (separate fast runner) |
| Detectable versions | `apps/web/package.json`; `node_modules/.pnpm/@next+env@16.2.9`; root `packageManager: pnpm@11.9.0` |
| Important constraints | `CLAUDE.md`: Node v24 for all FE work; stage and commit as separate commands. `rules/behavior.md`: surgical changes, no adjacent refactors. CI `web` job already pins `node-version: "24"` (see `docs/solutions/ci/pnpm-node-floor-mismatch.md`). |

---

## Feature Understanding and Assumptions

- **Requested feature:** revive the two Playwright specs behind the Supabase auth gate and run
  them on every PR in CI (design `specs/review-c1-e2e-auth-ci/design.md`, approved 2026-09-04).
- **What success appears to mean:** `pnpm e2e` green locally with creds and the BE up; a `web-e2e`
  CI job green on a PR; the same command exits 0 with everything skipped when creds are absent.
- **Assumptions from the request:** the e2e user is a real account on the project already
  configured in `apps/web/.env.local` (decision D1); no BE, middleware, or auth-action change.
- **Assumptions still needing confirmation:** that the human creates the Supabase e2e user with a
  **confirmed** email (an unconfirmed user cannot sign in with password, and `auth.setup.ts` would
  fail with `Email not confirmed`); and that repo secrets can be added (needed before the CI task
  can be verified at truth tier rather than by reading the workflow).

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `apps/web/playwright.config.ts` has a single `chromium` project, no `projects` dependency graph, `retries: 0`, `trace: "on-first-retry"` (so CI never captures a trace today), and a `webServer: pnpm dev` block with `reuseExistingServer: !process.env.CI`. |
| `Local` | `apps/web/playwright/trip-smoke.spec.ts:29` does `page.goto("/trips")` with no session; `theme.spec.ts` also uses `/trips` for 5 tests. |
| `Local` | `apps/web/src/lib/supabase/middleware.ts:14` gates `/trips /bookings /expenses /places`; `:60` redirects to `/auth/login`. `src/app/page.tsx` is `redirect("/trips")` and `AppShell.tsx:27` renders bare children under `/auth*` — so **no public URL renders the theme toggle**. |
| `Local` | `apps/web/src/app/auth/login/page.tsx:88,101` wrap the inputs in `<label><span>Email|Password</span><input>`, so `getByLabel("Email")` resolves; the form posts to the `signInWithPassword` server action, which returns `{ error }` and renders `role="alert"` on failure. |
| `Local` | `apps/web/src/lib/api/client.ts` attaches `Authorization: Bearer` via `authHeader()`; `apps/api/app/core/auth.py` verifies it against the project's JWKS (RS256/ES256) — so both the Next middleware and the BE need a **real** Supabase session; no local forgery. |
| `Local` | `.github/workflows/ci.yml` `web` job = checkout → pnpm → Node 24 → install → lint → vitest → build. No browser step, no BE step. `on: pull_request` only. |
| `Local` | `node_modules/.pnpm/@next+env@16.2.9` exists (transitive of `next` 16.2.9) but is **not** linked into `apps/web/node_modules`, so `require.resolve("@next/env")` from `apps/web` fails today. |
| `Docs` | Playwright auth guide prescribes exactly the design's shape: `{ name: 'setup', testMatch: /.*\.setup\.ts/ }` + `{ name: 'chromium', use: { storageState: 'playwright/.auth/user.json' }, dependencies: ['setup'] }`, storing state under `playwright/.auth/` and gitignoring it ("may contain sensitive cookies … used to impersonate you"). It also states the pattern fits parallel tests sharing one account when they don't clash — which matches `trip-smoke`'s unique-stamped trip. |
| `Docs` | Next.js env guide documents `@next/env` for "outside of the Next.js runtime, such as in a root config file for an ORM or **test runner**", tells you to install the package explicitly, and gives the load order: **`process.env` first** (so shell/CI vars win), then `.env.$(NODE_ENV).local`, then `.env.local`. |
| `Docs` | Same page: `.env.local` **is not checked when `NODE_ENV` is `test`**. Playwright does not set `NODE_ENV=test` itself, but anything that does (an editor task, a wrapper script) would silently blank the creds and turn every spec into a skip. |
| `Upstream` | microsoft/playwright#32302 "storageState is not working in GitHub Actions" — closed as *not planned*, i.e. user configuration (path / dependency ordering), not a framework bug. The practical lesson is to resolve the storage-state path absolutely rather than relying on the runner's cwd. |
| `Upstream` | Community practice splits two ways: sign in through the real UI once in a setup project (what this design does) or run a local Supabase stack in CI (`supabase-community/e2e`, `supawright`). The second was already rejected at intake (D1). |
| `Inference` | Sharing one e2e account across `fullyParallel` workers is safe **today** because each run stamps its trip title with `Date.now()`; it stops being safe the moment a spec asserts on a list of "all my trips". |

---

## Local Findings

- **Relevant files, modules, scripts, docs, tests:** `apps/web/playwright.config.ts`,
  `playwright/{theme,trip-smoke}.spec.ts`, `apps/web/package.json` (`e2e` script),
  `apps/web/.gitignore` (already ignores `/test-results`, `/playwright-report`,
  `/playwright/.cache` — **not** `/playwright/.auth`), `apps/web/.env.example`,
  `src/lib/supabase/{middleware,client,server,authHeader}.ts`, `src/app/auth/*`,
  `.github/workflows/ci.yml`, `apps/api/Makefile` (`dev` target = uvicorn recipe).
- **Existing abstractions or extension points:** the `webServer` block already boots Next and is
  already CI-aware; `authHeader()` is the single bearer seam; the `e2e` npm script is the single
  entry point. All three are extension points that need no change of shape.
- **Conventions worth preserving:** every spec carries a header comment with its exact run recipe
  (both existing specs do); env keys are documented in `.env.example`; CI jobs are flat and
  explicit rather than composite actions.
- **What can likely be reused:** the whole `webServer` config, the existing spec bodies (only a
  skip guard and a header edit), the CI `web` job's pnpm/Node setup block (copy, not share —
  `needs:` gives no shared filesystem), and the BE's documented uvicorn invocation.
- **What appears missing locally:** any auth fixture, any `projects` graph, any browser step in
  CI, `/playwright/.auth` in `.gitignore`, and a linked `@next/env`.

---

## Upstream Findings

- **Repositories inspected:** `microsoft/playwright` (issue tracker for the storageState-in-CI
  failure mode), `supabase-community/e2e` and `isaacharrisholt/supawright` (Supabase e2e harnesses).
- **Pattern or capability already present upstream:** the setup-project + `storageState` pattern is
  the framework's own documented answer; nothing needs adapting.
- **Files, modules, or areas worth modeling:** none to copy — the docs' snippet is smaller than any
  community wrapper.
- **How closely the upstream pattern matches this repo:** exactly, with one deviation: this repo
  must *skip* rather than fail when creds are absent, which upstream does not cover.
- **Any upstream gaps or uncertainties:** no upstream precedent found for the "skip cleanly on a
  fork PR" requirement; it is repo-specific glue (`playwright/e2e-env.ts` + step-level `if:`).

---

## Docs Findings

- **Official sources checked:** `playwright.dev/docs/auth`; `nextjs.org/docs/app/guides/environment-variables`.
- **Version-matched vs latest-stable status:** the Playwright auth page is the current stable doc
  and the installed 1.61.1 is newer than every API it shows (setup projects landed in 1.31); the
  Next.js page is served for 16.3.4 while the repo pins 16.2.9 — same major, and `loadEnvConfig`'s
  signature has been stable since Next 9, so the mismatch is immaterial.
- **Built-in capabilities that already support the feature:** project `dependencies`, per-project
  `storageState`, `testMatch`, file-scope `test.skip`, `trace`/`retries` — all built in; plus
  `loadEnvConfig` for the runner-side env.
- **Current recommended APIs or workflows:** exactly the design's D2/D3/D6 shapes.
- **Important caveats, deprecations, or migration notes:** (1) `.env.local` is skipped when
  `NODE_ENV=test`; (2) `process.env` outranks every file, which is what makes the CI path work
  without a `.env` file; (3) stored auth state must be gitignored and is not auto-expired — a stale
  `user.json` has to be deleted by hand (or written under `outputDir`).

---

## Recommendation

- **Primary recommendation:** **use built-in.** Implement the design as written: a `setup` project
  driving the real login form, a single `chromium` project consuming `storageState`, a shared
  `e2e-env.ts` for the collection-time skip, `loadEnvConfig(__dirname)` in the config, and a
  fully gated `web-e2e` CI job.
- **Why this is the lightest credible path:** every mechanism is first-party and documented for the
  installed versions; the diff is ~1 new small file plus edits to 6 existing ones, and no
  production code changes at all.
- **Why the next-best alternative lost:** a local Supabase stack in CI (`supabase` CLI, as
  `supabase-community/e2e` does) removes the secrets dependency but adds a multi-minute Docker
  boot to every PR **and** would have to satisfy `apps/api/app/core/auth.py`'s JWKS verification
  against the local stack's keys — a BE-config change the design explicitly rules out of scope.
  Programmatic sign-in via `supabase-js` lost because it would have to reproduce `@supabase/ssr`'s
  chunked cookie encoding by hand and would stop exercising the login page.
- **What would change this recommendation:** if the human cannot add repo secrets, the CI half
  becomes unverifiable and the work should be re-scoped to the local-only fix.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  1. *Relative `storageState` path* — the upstream failure mode in playwright#32302. Mitigate by
     building the path from `__dirname` in both `e2e-env.ts` and the config, never from cwd.
  2. *`NODE_ENV=test` blanks `.env.local`* — would silently turn a real local run into an all-skip
     run that still exits 0. Mitigate by having `e2e-env.ts` print one line naming where the creds
     came from (or their absence) so a skip is never silent.
  3. *Supabase rate limits / network flake in CI* — one sign-in per run keeps this small, but it is
     a real external dependency; `retries: 1` under CI covers a single transient failure.
  4. *Unconfirmed e2e user* — password sign-in fails; surfaces as a setup failure with the alert
     text, which is why the design attaches that text to the error.
  5. *Session file staleness locally* — a `user.json` older than the token lifetime makes `chromium`
     specs start signed-out; the setup project re-runs each `pnpm e2e`, so this only bites if a
     developer runs a single project with `--project=chromium`.
- **Evidence gaps:** no CI run has been executed with the new job; the skip-on-fork path is
  reasoned from the GitHub Actions `secrets`-in-job-`env` contract, not observed.
- **Version uncertainties:** `@playwright/test` is pinned as `^1.49` but resolves to 1.61.1 — the
  plan should pin the devDependency to the resolved line (or leave the caret and accept drift);
  this brief assumes the installed 1.61.1 behavior.
- **Follow-up questions for the user:**
  1. Confirm the Supabase e2e user's email is confirmed (or that you will confirm it) before the
     CI task's verification step.
  2. Do you want `@playwright/test` bumped from `^1.49` to `^1.61` while we are in this file, or
     left alone (surgical-change default)?

---

## Source Pack

- **Local files read:** `apps/web/playwright.config.ts`, `apps/web/playwright/theme.spec.ts`,
  `apps/web/playwright/trip-smoke.spec.ts`, `apps/web/package.json`, `apps/web/.gitignore`,
  `apps/web/.env.example`, `apps/web/next.config.ts`, `apps/web/src/lib/supabase/middleware.ts`,
  `apps/web/src/lib/supabase/authHeader.ts`, `apps/web/src/lib/api/client.ts`,
  `apps/web/src/lib/identity/provider.tsx`, `apps/web/src/app/auth/login/page.tsx`,
  `apps/web/src/app/auth/actions.ts`, `apps/api/app/core/auth.py`, `apps/api/app/core/config.py`,
  `apps/api/app/main.py`, `apps/api/Makefile`, `.github/workflows/ci.yml`, root `package.json`,
  `CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/*.md`, `docs/solutions/INDEX.md`,
  `docs/solutions/critical-patterns.md`, `docs/solutions/ci/pnpm-node-floor-mismatch.md`,
  `specs/review-c-web-experience/{SUMMARY,ESCALATIONS}.md`,
  `specs/review-a-security-hardening/{SUMMARY,design}.md`.
- **Upstream repositories or pages checked:**
  - https://github.com/microsoft/playwright/issues/32302
  - https://github.com/supabase-community/e2e
  - https://github.com/isaacharrisholt/supawright
- **Official docs domains or pages checked:**
  - https://playwright.dev/docs/auth
  - https://nextjs.org/docs/app/guides/environment-variables

---

## Evidence Boundary

> **Confirmed from artifacts:** the middleware gates `/trips` and no public page renders the theme
> toggle; both specs target `/trips`; CI has no browser or BE step; `@next/env@16.2.9` is in the
> pnpm store but unlinked from `apps/web`; Playwright resolves to 1.61.1; the login form's labels
> and the `role="alert"` failure path; the BE verifies bearers against Supabase JWKS; Playwright's
> and Next's documented shapes for both mechanisms and the `process.env`-wins load order.
>
> **Inferred from patterns:** that the fully-gated CI job reports green-with-skips on a fork PR;
> that one shared e2e account is safe under `fullyParallel` for these two specs; that the setup
> project's sign-in stays inside Supabase's rate limits.
>
> **Not checked:** no Playwright run was executed (chromium is not installed in this session and
> the BE was not running); no CI run; the Supabase e2e user does not exist yet; whether the repo's
> Actions secrets can be added by the author.
