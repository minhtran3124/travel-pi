# UAT — dashboard authentication (PR #144, `specs/dashboard-auth-required`)

**Date:** 2026-09-07
**Branch:** `feat/dashboard-auth-required` @ `b551cc3` (after merging `main` @ `8f84da6`)
**Environment:** two local uvicorn processes started from this worktree on fresh SQLite databases, driven by headless Chromium (playwright-core 1.60):

| Port | `DASHBOARD_BASIC_USER` / `_PASSWORD` / `_SECRET_KEY` | Purpose |
|---|---|---|
| 8010 | set (user `admin`, 32-byte hex secret) | the configured server — every login use case |
| 8011 | unset | the "locked" server — proves the guard is always on |

The agent graph failed to build on both servers (`OPENAI_API_KEY` not set); that only disables `/agent/*` and is unrelated to the dashboard.

## Automated suite (re-run before the UAT)

```
cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_dashboard_auth.py \
  tests/api/agent_config/test_dashboard_auth.py tests/api/agent_config/test_login_template.py \
  tests/api/agent_config/test_agent_runs_dashboard.py tests/api/agent_config/test_agent_run_detail_page.py -q
# 87 passed
```

## Use cases

| # | Use case | Expected | Observed | Screenshot |
|---|---|---|---|---|
| 1 | Logged-out visit to `/dashboard` | 303 to `/dashboard/login?next=%2Fdashboard` | landed on `/dashboard/login?next=%2Fdashboard` | `01-unauth-dashboard-redirects-to-login.png` |
| 2 | Wrong password | 401, form re-rendered with an error, no cookie | `POST` → 401, "Invalid username or password", still on the login URL | `02-wrong-password-shows-error.png` |
| 3 | Correct credentials | 303 to `/dashboard`, session cookie set, **Log out** in the top bar | `POST` → 303, landed on `/dashboard`; cookie `dashboard_session` path=`/dashboard` HttpOnly SameSite=Lax (Secure off: dev) | `03-login-success-dashboard-with-logout.png` |
| 4 | Signed-in user opens `/dashboard/login` | bounced to `/dashboard` | landed on `/dashboard` | `04-signed-in-login-page-redirects-to-dashboard.png` |
| 5 | Click **Log out** | 303 to `/dashboard/login`, cookie cleared | `POST /dashboard/logout` → 303, browser cookie jar no longer holds `dashboard_session` | `05-logout-returns-to-login.png` |
| 6 | `/dashboard` right after logout | redirected to login again | landed on `/dashboard/login?next=%2Fdashboard` | `06-after-logout-dashboard-locked-again.png` |
| 7 | Deep link `/dashboard/prompts` while logged out | login page carries `next=%2Fdashboard%2Fprompts` | as expected | `07-deep-link-prompts-redirects-with-next.png` |
| 8 | …then log in | lands on `/dashboard/prompts`, not the home page | `POST` → 303, landed on `/dashboard/prompts` | `08-deep-link-lands-on-prompts-after-login.png` |
| 9 | Open redirect: `/dashboard/login?next=https://evil.example/phish` | `next` ignored, lands on `/dashboard` | landed on `/dashboard` | `09-open-redirect-blocked-lands-on-dashboard.png` |
| 10 | Forged cookie (`alg=HS256`, unsigned payload `sub=admin`) | rejected, redirected to login | landed on `/dashboard/login?next=%2Fdashboard` | `10-tampered-cookie-rejected.png` |
| 11 | API client (`Accept: application/json`, no cookie) | 401 JSON, **not** a redirect | 401 `{"error":"DashboardLoginRequired", …}` | `11-json-client-gets-401-json.png` (rendered from the raw HTTP response) |
| 12 | Server without credentials (port 8011) | dashboard locked: login page shows a notice, submit disabled, `POST` refused | notice "Dashboard login is not configured on this server", button disabled, `POST /dashboard/login` → 401; startup log: `WARNING: Dashboard locked: set DASHBOARD_BASIC_USER, DASHBOARD_BASIC_PASSWORD, DASHBOARD_SECRET_KEY to enable login at /dashboard` | `12-unconfigured-server-login-locked.png` |

## Raw headers (curl against port 8010)

```
POST /dashboard/login  (valid credentials)
HTTP/1.1 303 See Other
location: /dashboard
set-cookie: dashboard_session=<jwt>; HttpOnly; Max-Age=43200; Path=/dashboard; SameSite=lax

POST /dashboard/logout
HTTP/1.1 303 See Other
location: /dashboard/login
set-cookie: dashboard_session=""; expires=Mon, 07 Sep 2026 01:03:09 GMT; HttpOnly; Max-Age=0; Path=/dashboard; SameSite=lax
```

The cleared cookie carries the same `Path`/flags as the one that was set, so browsers actually drop it (use case 5/6).

## Verdict

**PASS** — all 12 use cases behaved as specified (SC-1…SC-9 of the plan), on top of the 87 automated tests.
