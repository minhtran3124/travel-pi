# review-c1-e2e-auth-ci — Summary

Lane: high-risk
Confidence: high
Reason: auth hard gate (Playwright login fixture must obtain a Supabase session and pass the /trips middleware redirect) plus flags weak proof, external systems (Supabase auth + GitHub Actions), existing behavior. Test/CI-only code, but the gate vocabulary matches, so the lane stays high-risk rather than being lowered by narrowing.
Flags: auth, weak proof, external systems, existing behavior
Affects: apps/web/playwright/*, apps/web/playwright.config.ts, .github/workflows/ci.yml (web job), apps/web/src/lib/supabase/middleware.ts (read-only reference)
Input-type: spec slice
Route: high-risk — brainstorming (fixture strategy: real Supabase test user vs mocked session cookie vs storageState) → xia2 (Deep; external surface: Playwright + Supabase auth) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no (parent ESCALATIONS E001–E003 decided 2026-09-04; see ../review-c-web-experience/ESCALATIONS.md)
Parent: review-c-web-experience

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> chay /feature-intake cho section "C. Web app & trải nghiệm" theo artifact link https://claude.ai/code/artifact/e31c4a78-8e78-4b47-9ec7-4e9c5d0d2ac1?via=auto_preview
>
> (follow-up, 2026-09-04) 1. ok  2. lam hop dong BE  3. backlog A

Slice of the parent intent (verbatim review text in `../review-c-web-experience/SUMMARY.md` § Intent):

> Item 10 (remaining half): 2 Playwright specs / 6 tests not in CI; `trip-smoke.spec.ts` hits `/trips` unauthenticated while the middleware now redirects to `/auth/login`, so it is almost certainly broken. (The "identity hai đầu" half is already fixed on main by review-A / PR #129 — not in scope.)
>
> Goal: a login fixture, `trip-smoke` + `theme` green locally, and an e2e job in CI.

## What changed

Both Playwright specs run again behind the Supabase auth gate, and the browser suite now runs on
every pull request. A setup project signs in once through the real login form and saves the
session; a chromium project reuses it. Without credentials every spec skips at collection instead
of failing, so a fork's pull request reports a green job with every step skipped. Eight plan tasks,
six commits, no production code touched.

### Rationale

Playwright's own setup-project pattern and Next's own env loader cover the whole requirement, so
the work is glue rather than invention. The credentials come from the existing Supabase project
because both the Next middleware and the API verify tokens against that project's public keys, so
a session cannot be forged locally; a local Supabase stack would have meant a backend config
change the design ruled out.

### Alternatives considered

- Programmatic sign-in through `supabase-js`: would have to reproduce the chunked cookie encoding
  of `@supabase/ssr` by hand and would stop exercising the login page.
- A local Supabase stack in CI: removes the secrets dependency but adds a multi-minute Docker boot
  to every pull request and would have to satisfy the API's JWKS verification against the local
  stack's keys.

### Deviations

- Rule 1 — `trip-smoke.spec.ts` targeted `getByLabel("Title")` on the New-trip dialog, but that
  field is labeled "Trip name" (`messages/en.json` `newTripModal.tripNameLabel`) — "Title" only
  exists in the unrelated itinerary Add-item form. The auth gate always failed the spec before it
  reached that line, so the mismatch was never exercised; it predates this branch (commit
  `f22f02a`). Found by running the suite green end to end for the first time; fixed and verified
  in `9abf0d0`.
- Rule 3 — Added the devDependency `@next/env@16.2.9` to `apps/web/package.json`, pinned to the
  version `next` already resolves. The package was already in the pnpm store as a transitive of
  `next` but was not linked into `apps/web`, so `playwright.config.ts` could not import
  `loadEnvConfig`. Commit `a8b3bf2`.
- Rule 1 — Task 2.1's module originally derived its path from `import.meta.url`, as `PLAN.md`
  mandated. That is a parse error under Playwright's CommonJS transpile, so the module is anchored
  on `__dirname` behind a `typeof` guard and the plan was corrected. Commit `1a3fb62`.
- Rule 1 — The config's `loadEnvConfig(__dirname)` statement ran after `e2e-env` had already read
  `process.env`, so credentials present only in `apps/web/.env.local` were captured as undefined
  and every spec skipped while exiting 0. Split into `playwright/load-env.ts` (imported first, dev
  mode) and `playwright/storage-state.ts` (throws rather than a cwd-relative fallback). Found by
  the wave-3 task review. Reproduced before fixing by writing a temporary `.env.development.local`
  with credentials and running `pnpm exec playwright test --list --project=setup`: the
  missing-credentials notice still printed. After the fix the notice is gone. The probe file was
  deleted; it is deliberately not a `### Verify` row because running it would mutate the working
  tree. Commit `6f4a2af`.
- Design deviation — `STORAGE_STATE` is an absolute path derived from the module URL, where
  `design.md` D2 wrote the relative `"playwright/.auth/user.json"` the Playwright docs show. A
  cwd-relative storage-state path is the documented cause of the setup project passing locally and
  failing on a CI runner (microsoft/playwright#32302). Recorded in `PLAN.md` Task 2.1 and Risks.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| `@next/env` resolves from the web package | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec node -e "require.resolve('@next/env')"` | 0 | re-run by the controller at `c9deca3` | SC-1 |
| Auth state ignored, credentials documented | `grep -q E2E_USER_EMAIL apps/web/.env.example && git check-ignore -q apps/web/playwright/.auth/user.json` | 0 | | SC-2 |
| No credentials in the environment reports none | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && env -u E2E_USER_EMAIL -u E2E_USER_PASSWORD pnpm --filter @travel/web exec node -e "import('./playwright/e2e-env.ts').then(m => process.exit(m.hasCreds === false ? 0 : 1))"` | 0 | | SC-3 |
| Both credentials set report present | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && E2E_USER_EMAIL=e2e@example.com E2E_USER_PASSWORD=pw pnpm --filter @travel/web exec node -e "import('./playwright/e2e-env.ts').then(m => process.exit(m.hasCreds === true ? 0 : 1))"` | 0 | | SC-4 |
| Both specs collect under a chromium project depending on setup | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec playwright test --list --project=chromium` | 0 | 7 tests in 3 files, `[setup]` listed first | SC-5 |
| Web package type-checks, Playwright directory included | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec tsc --noEmit` | 0 | | SC-6 |
| CI job gated on the secrets flag | `python3 -c "import yaml; j=yaml.safe_load(open('.github/workflows/ci.yml'))['jobs']['web-e2e']; s=j['steps']; assert 'web' in j['needs'] and 'HAS_E2E_SECRETS' in j['env']; assert sum(1 for x in s if 'HAS_E2E_SECRETS' in str(x.get('if',''))) == len(s) - 1"` | 0 | exits 1 on the pre-branch tree | SC-7 |
| Full e2e suite passes with real credentials against a live backend | `pnpm --filter @travel/web e2e` | 0 | Supabase e2e user `e2e-test@travel-pi.local` (id `e1009927-e78b-4afc-9aa4-78c64cbb59cd`), creds in `.env.local`, backend on `:8000`/SQLite: 7 passed (setup + 5 theme + trip-smoke), 0 failed, ~5s | |
| No regression in the fast runner | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web test` | 0 | 178 passed | |
| Lint clean | `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web lint` | 0 | | |
E2E_USER_PASSWORD=…
' > apps/web/.env.development.local && export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && pnpm --filter @travel/web exec playwright test --list --project=setup` | 0 | printed the missing-credentials notice despite the file; after the fix the notice is gone. Probe file deleted. | |

### Not auto-verified

- The intake corroboration of item 10 (Playwright absent from CI, `trip-smoke` opening `/trips`
  unauthenticated) described the pre-branch tree, so it is no longer re-runnable here. It stands
  recorded in `../review-c-web-experience/SUMMARY.md`.
- The Supabase e2e user was created (`e2e-test@travel-pi.local`, confirmed email) and the four
  repository secrets were set on 2026-09-04, closing the human prerequisites `design.md` named.
  The full suite was then run locally against a live backend: 7 passed, 0 failed — see the new
  `### Verify` row above. This is truth-tier for the local half. The CI half (`web-e2e` actually
  passing on GitHub Actions) is being watched on PR #135 as of this commit; not yet closed here.
- "The lockfile diff adds only the `@next/env` link" — reached provenance: every changed line was
  read and no resolved version moves, but `pnpm install` also re-normalized three peer-context keys
  with a `(supports-color@10.2.2)` qualifier and added a `deprecated:` note on the existing
  `eslint@9.39.4`. The Done wording means "no version changes", not "a one-line diff".

### Correctness review

Six angles ran over the full branch diff. Findings that survived verification, all fixed in
`a1e4e5a`:

| Finding | Why it mattered | Angle(s) |
| --- | --- | --- |
| An explicit `if:` replaces the implicit `success()` guard in GitHub Actions, so every gated step kept running after an earlier one failed | A backend that never booted still installed a browser and ran the suite; the real error hid behind a timeout | enclosing-function |
| The secrets flag consulted one of the four secrets the job uses | Email-only config ran everything and reported green with all tests skipped; missing Supabase values crashed the dev server instead of skipping | enclosing-function, guard-completeness, call-site-impact |
| The `list` reporter writes no `playwright-report/`, and CI retry traces land in `test-results/`, which nothing uploaded | A CI failure produced no retrievable trace or report | enclosing-function, removed-behavior, call-site-impact |
| `retries: 1` under CI defeats the no-FOUC test's single-attempt design | A real theme flash would be reported flaky and the run would exit 0 | removed-behavior |
| `waitForURL` had no explicit bound, so the test deadline expired before its diagnostic branch | A wrong password surfaced as a bare timeout instead of the alert text | guard-completeness |
| `cat uvicorn.log` failed when the log did not exist | A second red step competed with the real failure | guard-completeness, enclosing-function |

One candidate was rejected on evidence: `-g "theme"` was reported to filter the `setup` project out
and leave the specs without a storage state. Running `playwright test --list -g "theme"` shows the
`[setup]` entry still present, and Playwright 1.61 re-adds dependency projects from the unfiltered
project map. No change made.

One finding survived past the first fix commit: the diagnostic steps were gated on `failure()`
alone, so a job GitHub Actions cancels for hitting `timeout-minutes` (rather than failing) — the
exact hang the timeout exists to bound — skipped both the backend log and the report/trace upload.
Fixed in `0056940` with `(failure() || cancelled())`.

`prior-art` found nothing: the pnpm/Node floor lesson in `docs/solutions/ci/` is respected by the
new job (Node 24).

### Intent Findings

Update (2026-09-04, after the intent review ran): both external prerequisites now exist — the
Supabase e2e user was created and the four repository secrets were set. GAP-1 is closed by the new
local Verify row (7 passed, 0 failed). GAP-2 is closed by a real GitHub Actions run: `web-e2e`
passed on PR #135 (run 33861006479, 1m29s). Both gaps closed 2026-09-04.

Intent review verdict at time of review: **gaps found** (proof gaps only — no drift, no excess). Both gaps are
external-prerequisite blockers already disclosed in this SUMMARY and `design.md` § Human
prerequisites; deferred rather than escalated because the direction is unambiguous, only blocked on
state this session cannot create.

- **GAP-1 — "trip-smoke + theme green locally" unproven.** No `### Verify` row runs
  `pnpm --filter @travel/web e2e`; SC-5 only collects. Closes when the Supabase e2e user and
  `apps/web/.env.local` credentials exist and the manual acceptance in `PLAN.md` §3 is run.
- **GAP-2 — the CI job is inert on this repository today.** `HAS_E2E_SECRETS` requires four
  secrets none of which are set, so `web-e2e` reports green having run only the notice step. Closes
  when the four repository secrets are added.

Both require the human prerequisites named in `design.md`; this session has no path to them.

### Rollback

- Intake only so far: `git rm -r specs/review-c1-e2e-auth-ci`. Implementation commits: `git revert <sha>` per task (to be filled by SDD).

### Harness-Delta

- none
