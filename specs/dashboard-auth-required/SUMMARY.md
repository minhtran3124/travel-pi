# dashboard-auth-required — Summary

Lane: high-risk
Confidence: low
Reason: Manifest hard gate `auth` (login/password/sessions) fires by definition; the request has three materially different readings against a guard that already exists (see ESCALATIONS.md E001).
Flags: auth, audit/security, existing behavior
Affects: app/core/dashboard_auth.py (require_dashboard_access), app/routers/dashboard.py, app/routers/dashboard_prompts.py, app/core/config.py (dashboard_basic_user/password), .env.example
Input-type: change request
Route: brainstorming → xia2 → writing-plans → using-git-worktrees → subagent-driven-development (E001 decided: C)
Escalate: yes (hard gate `auth` + low confidence — direction ambiguous)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

plan to add simple authentication (username/pass) for the dashboard. Require authen when access the dashboard page.

## What changed

Intake only — no code changed. Finding: the dashboard is **already** guarded by HTTP Basic
username/password (shipped in `specs/review-a-security-hardening`, PR #129):

- `app/core/dashboard_auth.py::require_dashboard_access` is attached as a router-level
  `dependencies=[Depends(...)]` on both `/dashboard` routers (`dashboard.py`,
  `dashboard_prompts.py`), which are the only routes under the `/dashboard` prefix.
- Behaviour is opt-in via `DASHBOARD_BASIC_USER` + `DASHBOARD_BASIC_PASSWORD`: both set →
  401 + `WWW-Authenticate: Basic` on any `/dashboard/*` request without valid creds (browser
  prompts); neither set → open in development, 404 in production (`ENVIRONMENT=production`).
- Covered by `tests/api/agent_config/test_dashboard_auth.py` (4 states).
- The local `apps/api/.env` does not set the two vars, so the dev dashboard currently opens
  without a prompt — which is most likely why the request was raised.

### Rationale

Auth is a block-mode hard gate in `.claude/harness-manifest.json`, so the lane is high-risk
regardless of size. Confidence is low because the "right" work ranges from zero code (set env)
to a new login-form + cookie-session surface that review-A explicitly listed as a non-goal
("Admin-JWT dashboard login"). Picking silently would either do nothing useful or build an
unrequested surface.

### Alternatives considered

- A) No code: set `DASHBOARD_BASIC_USER`/`PASSWORD` in `apps/api/.env` (and Docker env) — already meets "username/pass, required on access".
- B) Make the guard **always-on**: drop the open-in-dev branch (401 in every environment, or fail startup when creds are unset). Small change to `dashboard_auth.py` + `Settings` validator + tests + `.env.example`.
- C) Replace the browser Basic prompt with a **login page** (`/dashboard/login` form, signed cookie session, logout). New template + session handling; largest surface.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| existing guard suite | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q` | 0 | 8 passed (pre-existing coverage of the current guard) | |

### Not auto-verified

- "both `/dashboard` routers are the only `/dashboard` routes" — reached traceability (grep of `prefix="/dashboard"` in `app/routers/`); not re-run against the live route table.

### Advisory Findings

Correctness-review (six-angle find + independent score, threshold 75, floor 60) ran over the
full implementation diff (`0f9d2ed..HEAD`). All four deduplicated candidates scored below
threshold and were NOT auto-fixed, per the pipeline's below-threshold routing rule:

| Location | Claim | Score | Why capped |
|---|---|---|---|
| `app/core/dashboard_auth.py` `safe_next` | `next=/dashboard/login/` (trailing slash) is not excluded by the exact-string check, so Starlette 307-redirects it back to `/dashboard/login` after a valid login | 25 | The session cookie is already set by then, so `GET /dashboard/login` sees the valid cookie and 303s straight to `/dashboard`; extra redirect hop only, no security or correctness impact |
| `app/routers/dashboard_login.py` `login_form` | Calls `get_current_dashboard_user(token)` as a plain function instead of via `Depends(...)`, so `app.dependency_overrides` (used by the shared test `client` fixture) does not apply to the login page | 25 | Production behaviour is correct (cookie still validated identically); no shipped test exercises `GET /dashboard/login` through the shared fixture — a latent testability wart, not a manifest defect |
| `app/core/dashboard_auth.py` `missing_credentials` | `secret.encode()` on a `DASHBOARD_SECRET_KEY` containing lone surrogate codepoints (invalid UTF-8 injected directly into `os.environ`, bypassing `.env`) raises an uncaught `UnicodeEncodeError` → 500 instead of the documented locked/notice behaviour | 25 | Requires an OS-level env injection that bypasses `.env`'s own UTF-8 decoding; exotic and unverifiable from this repo |
| `app/templates/login.html` form `action="{{ request.url }}"` | Reflects the incoming `Host` header (no `TrustedHostMiddleware` is registered anywhere in `apps/api`); an attacker-controlled `Host` could point the submitted username/password at a different origin | 50 | Mechanism is real and verifiable in-repo (no trusted-host guard exists); capped because exploitability depends on unverifiable deployment/proxy topology |

None reached the 75 threshold, so none entered the fix loop. Recorded here per the pipeline's
"nothing is silently dropped" rule. The `login.html` finding (score 50) is the one worth acting
on if the dashboard is ever exposed without a reverse proxy that normalizes `Host` — swap
`action="{{ request.url }}"` for a relative path/query.

### Rollback

- none yet (intake only). Any implementation: `git revert <sha>`; option A is undone by unsetting the two env vars.

### Harness-Delta

- none
