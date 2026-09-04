# review-c1-e2e-auth-ci — Design

Status: approved by the user in-session (2026-09-04). Parent: `specs/review-c-web-experience/`
(E001-A slice 1). Source: Travel-Pi Deep Review §3.C item 10, E2E half only.

## Agreed purpose, constraints, approach

Bring the two Playwright specs back to life behind the Supabase auth gate and run them in CI on
every PR. The session comes from the **existing Supabase project with a dedicated e2e user**; the
fixture signs in **once through the real `/auth/login` form** and shares the resulting cookies via
Playwright `storageState`; the CI job **self-skips when the e2e secrets are absent** (fork PRs)
instead of failing. No change to middleware, auth server actions, or the BE.

## Problem

- `apps/web/playwright/trip-smoke.spec.ts:29` opens `/trips` with no session; since review-A the
  middleware (`src/lib/supabase/middleware.ts:14,60`) redirects `/trips` → `/auth/login`, so the
  spec can only fail.
- `theme.spec.ts` also uses `/trips`, so it is redirected too. There is no public page that renders
  the header toggle: `/` is `redirect("/trips")` (`src/app/page.tsx`) and `AppShell.tsx:27` renders
  bare children (no header, no `ThemeToggle`) under `/auth*`. So every existing e2e needs a session.
- `.github/workflows/ci.yml` web job runs lint / vitest / build only; nothing exercises the
  browser → Next → `/api/be` proxy → FastAPI → SQLite path.
- Both the Next middleware (`getClaims()`) and the BE (`app/core/auth.py`, JWKS RS256/ES256)
  verify tokens against the real project's public keys, so a session cannot be forged locally.

## Decisions (WHAT)

| # | Decision | Consequence |
|---|---|---|
| D1 | Auth source: the existing Supabase project (`NEXT_PUBLIC_SUPABASE_URL` in `.env.local`) plus one dedicated e2e user (email + password, email confirmed). | Human prerequisite: create the user in the Supabase dashboard. Creds live only in `.env.local` (local) and GitHub Actions secrets (CI). |
| D2 | Sign-in fixture: a Playwright **setup project** (`playwright/auth.setup.ts`) drives the real `/auth/login` form once and saves `playwright/.auth/user.json`; authed specs reuse it via `storageState`. | Proves the login page works as a side effect. `.auth/` is gitignored. This is the "globalSetup through the form" the user chose, implemented as the 1.49-recommended setup project so it gets trace/report. |
| D3 | Two projects in `playwright.config.ts`: `setup` (`testMatch: /.*\.setup\.ts/`) and `chromium` (`storageState: "playwright/.auth/user.json"`, `dependencies: ["setup"]`, both specs). | Both specs keep `/trips`; the header + toggle render there even while trip data loads, so `theme.spec.ts` needs a session but still not the BE. No hermetic project: with no creds nothing runs (see D4). |
| D4 | Missing creds ⇒ skip, not fail. A shared `playwright/e2e-env.ts` exports `hasCreds` (both `E2E_USER_EMAIL` and `E2E_USER_PASSWORD` set). `auth.setup.ts`, `theme.spec.ts` and `trip-smoke.spec.ts` each call **file-scope** `test.skip(!hasCreds, "E2E_USER_EMAIL/PASSWORD not set")` — evaluated at collection, before the `context` fixture would try to read the missing `.auth/user.json`. | `pnpm e2e` with no creds exits 0 with all tests reported skipped; a `test.skip` inside a test body would be too late (fixture `ENOENT`). |
| D5 | CI: new job `web-e2e` (`needs: web`, fresh runner so it repeats the Python/uv and Node/pnpm setup). Job-level `env.HAS_E2E_SECRETS: ${{ secrets.E2E_USER_EMAIL != '' }}`; **every step** carries `if: env.HAS_E2E_SECRETS == 'true'` except a final unconditional `echo "e2e skipped: no secrets"`. Steps: checkout → setup-python 3.12 + uv → `uv venv && uv pip install -r requirements.txt` → start `nohup uvicorn app.main:app --port 8000 > uvicorn.log 2>&1 &` (detached, or it dies with the step shell) with `DATABASE_URL=sqlite:///./e2e.db`, `SUPABASE_URL` (JWKS), `ENVIRONMENT=development`, every LLM key empty, then in the same step `curl -sf http://localhost:8000/docs` in a loop (max 60 s, `exit 1` + `cat uvicorn.log` on timeout so a BE boot failure fails at this step, not as a proxy 502 in the smoke test) → pnpm setup + `pnpm install --frozen-lockfile` → `pnpm --filter @travel/web exec playwright install --with-deps chromium` → `pnpm --filter @travel/web e2e` with `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_API_URL=http://localhost:8000`, `E2E_USER_EMAIL`, `E2E_USER_PASSWORD` → `actions/upload-artifact` of `apps/web/playwright-report` on failure. | On a fork PR the job is green with every step skipped; nothing boots Next without `NEXT_PUBLIC_SUPABASE_*` (which would crash the dev server). Secrets: `E2E_USER_EMAIL`, `E2E_USER_PASSWORD`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. Next runs via the existing `webServer: pnpm dev`; `reuseExistingServer` is already off under `CI`. No explicit uvicorn teardown: the runner ends the job. |
| D6 | Local creds come from `apps/web/.env.local`, loaded in `playwright.config.ts` with `loadEnvConfig(__dirname)` from `@next/env` — the same loader Next uses, so precedence matches `pnpm dev`. `@next/env` is in the pnpm store (16.2.9, transitive of `next`) but not linked into `apps/web`, so it is added as an explicit devDependency pinned to `next`'s version. Existing shell env still wins (loader never overrides set vars), which is what CI relies on. | `package.json` edit trips the external-provider gate; the lane is already high-risk and no network download occurs. `.env.local` stays gitignored. |
| D7 | No test-data cleanup. CI uses a fresh SQLite file per run; locally the e2e user accumulates `E2E Trip <stamp>` rows, which are owner-scoped and harmless. | Revisit only if local runs become slow. |

## Out of scope (non-goals)

- Programmatic sign-in via supabase-js, local Supabase stack, or a BE test-token path.
- New e2e coverage beyond the two existing specs (chat, bookings, places).
- Running Next as `build` + `start` in CI (kept `pnpm dev` for parity with the existing config).
- Anything from items 11–12 (siblings `review-c2-*`, `review-c3-*`).
- The stale "identity hai đầu" claim — already fixed by review-A (PR #129).

## Components and data flow (HOW)

```
CI job web-e2e
  ├─ uvicorn app.main:app :8000  (SQLite e2e.db, SUPABASE_URL → JWKS)
  └─ playwright test
       ├─ project setup    : auth.setup.ts → /auth/login form → cookies → .auth/user.json
       └─ project chromium : theme.spec.ts + trip-smoke.spec.ts (storageState)
              browser → Next :3000 (middleware getClaims ✓) → /api/be proxy
              → FastAPI (bearer from authHeader() ✓ JWKS) → SQLite
```

Units:

- `playwright/e2e-env.ts` — exports `E2E_USER_EMAIL`, `E2E_USER_PASSWORD`, `hasCreds`,
  `STORAGE_STATE` path. Single place that reads the env.
- `playwright/auth.setup.ts` — file-scope skip on `!hasCreds`; one `setup()` test: goto
  `/auth/login`, fill `Email`/`Password` (labels in `src/app/auth/login/page.tsx:88,101`), submit,
  `waitForURL` off `/auth/login` wrapped so that on timeout the `role="alert"` text (if any) is attached to the thrown error, then `context.storageState({ path })`.
- `playwright.config.ts` — `loadEnvConfig(__dirname)` at the top (D6); `retries: process.env.CI ? 1 : 0` so `trace: "on-first-retry"` actually yields a trace in CI; `projects: [setup, chromium]`; `chromium` has `storageState` +
  `dependencies: ["setup"]`; `testMatch` keeps `*.setup.ts` out of `chromium`.
- `playwright/theme.spec.ts` — add the file-scope skip and the header recipe (note: a pass-on-retry of
  the no-FOUC test under CI `retries: 1` is still a real flash signal, check the trace); page and
  assertions untouched.
- `playwright/trip-smoke.spec.ts` — add the file-scope skip; header recipe updated; flow untouched.
- `apps/web/.gitignore` — add `/playwright/.auth`.
- `apps/web/.env.example` — document `E2E_USER_EMAIL`, `E2E_USER_PASSWORD`.
- `apps/web/package.json` — `devDependencies["@next/env"] = "16.2.9"` (D6); lockfile updated.
- `.github/workflows/ci.yml` — job `web-e2e` (D5).

## Error behavior

| Situation | Behavior |
|---|---|
| Creds absent locally | Every test skipped with reason at collection; exit 0; no fixture touches `.auth/user.json`. |
| Creds absent in CI (fork PR) | Job green, all steps skipped, final echo explains why. |
| Wrong creds / login form error | `auth.setup.ts` fails at `waitForURL` with the alert text attached; `chromium` specs do not run (dependency failed). |
| BE fails to boot in CI | The start+poll step exits 1 and prints `uvicorn.log`. |
| BE not started locally | Unchanged: trip-smoke fails on the `/api/be` proxy error; header recipe says how to start it. |
| Supabase unreachable in CI | Login fails as above; job fails visibly (external dependency accepted in D1). |
| Stored session expired between setup and spec | Not expected within one run (Supabase access token ≥ 1 h); the SDK refreshes on `getSession()`. |

## Tests / verification

- Local: `pnpm e2e` green for `setup` + `chromium` with creds in `.env.local` and the BE on `:8000`;
  `pnpm e2e` with creds unset exits 0 with every test skipped.
- CI: `web-e2e` green on this branch's PR (secrets configured by the human beforehand).
- The no-secrets path in CI is verified by reading the workflow, not by a real run (recorded in
  `SUMMARY.md` § Not auto-verified).

## Human prerequisites (before execution)

1. Create the e2e user in the Supabase project (email confirmed, password set).
2. Add the four GitHub Actions secrets listed in D5.
3. Add `E2E_USER_EMAIL` / `E2E_USER_PASSWORD` to `apps/web/.env.local`.
