# dashboard-auth-required — Summary

Lane: high-risk
Confidence: low
Reason: Manifest hard gate `auth` (login/password/sessions) fires by definition; the request has three materially different readings against a guard that already exists (see ESCALATIONS.md E001).
Flags: auth, audit/security, existing behavior
Affects: app/core/dashboard_auth.py, app/routers/dashboard.py, app/routers/dashboard_prompts.py, app/routers/dashboard_login.py (new), app/core/errors.py, app/core/lifespan.py, app/core/config.py, app/templates/login.html (new), app/templates/base.html, .env.example
Input-type: change request
Route: brainstorming → xia2 → writing-plans → using-git-worktrees → subagent-driven-development (E001 decided: C)
Escalate: yes (hard gate `auth` + low confidence — direction ambiguous)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

plan to add simple authentication (username/pass) for the dashboard. Require authen when access the dashboard page.

## What changed

Replaced the HTTP Basic guard on `/dashboard/*` (shipped in `specs/review-a-security-hardening`,
PR #129) with a login page backed by a signed session cookie, per escalation E001 → option C:

- `app/core/dashboard_auth.py` rewritten around FastAPI's `APIKeyCookie` and a PyJWT HS256
  session token (`sub`/`iat`/`exp`, `algorithms=["HS256"]`, `leeway=60`,
  `options={"require": ["exp", "iat", "sub"]}`), signed with a new `DASHBOARD_SECRET_KEY`
  setting (≥32 bytes, or the dashboard is treated as unconfigured).
- New router `app/routers/dashboard_login.py`: `GET/POST /dashboard/login`,
  `POST /dashboard/logout`, unguarded, using `OAuth2PasswordRequestForm` for the credential
  fields.
- `DashboardLoginRequired` (an `AuthError` subclass) is handled inside
  `register_exception_handlers` (`app/core/errors.py`): an HTML request gets a `303` to the
  login page; any other request gets the existing 401 JSON envelope.
- Both dashboard routers now guard with `get_current_dashboard_user` instead of
  `require_dashboard_access`.
- Auth is **always required**: the old "open in development" and "404 in production without
  creds" branches are gone. With any of the three env vars missing (or a secret under 32
  bytes) the dashboard is locked — every page redirects to the login screen, which shows a
  "not configured" notice — and `lifespan` logs a startup warning naming the missing vars.
  The server does not refuse to start.
- New `app/templates/login.html` and a logout button in `base.html`'s topbar.
- `.env.example` documents all three vars and `openssl rand -hex 32`.
- `tests/conftest.py`'s shared `client` fixture and two per-`Settings` dashboard-page test
  modules were updated to authenticate via a session cookie instead of relying on the removed
  open/404 branches; `tests/api/agent_config/test_dashboard_auth.py` was rewritten as ten
  cases covering unconfigured credentials, unauthenticated HTML vs JSON requests, login,
  rejection/forgery/expiry, `next`-url sanitisation, logout, and the `Secure` flag.

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

- Rule 2 — `create_session_token` refuses to issue a token when credentials are unconfigured
  (guards against `jwt.encode` ever seeing a sub-32-byte or missing secret). Found during
  Task 1.1 per-task review. `app/core/dashboard_auth.py`, commit `49bdc2a`.
- Rule 1 — two invalid `font: <weight> <size> inherit` CSS shorthands in `login.html`/`base.html`
  (a CSS-wide keyword cannot be a shorthand component; the browser drops the whole declaration)
  replaced with explicit longhands, and the topbar logout button sized to match its neighbours.
  Found during Task 1.2 per-task review. `app/templates/login.html`, `app/templates/base.html`,
  commit `49bdc2a`.
- Rule 1 — hoisted a function-local `from app.exceptions import AuthError` to the module header
  in `tests/core/test_dashboard_auth.py`. Found during Task 1.1 per-task review, commit `49bdc2a`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| token/cookie unit tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_dashboard_auth.py -q` | 0 | 51 passed | SC-1 |
| unauthenticated redirect/JSON | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q -k test_unauth` | 0 | 2 passed | SC-2 |
| login sets session cookie | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q -k test_login` | 0 | 2 passed | SC-3 |
| rejected/forged sessions + next sanitisation | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q -k "test_reject or test_next"` | 0 | 13 passed | SC-4 |
| unconfigured credentials lock the dashboard | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q -k test_unconfigured` | 0 | 4 passed | SC-5 |
| logout + Secure-by-environment | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q -k "test_logout or test_secure"` | 0 | 3 passed | SC-6 |
| existing dashboard pages still render | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py tests/api/prompts/test_dashboard_prompts.py tests/api/agent_config/test_agent_runs_dashboard.py tests/api/agent_config/test_agent_run_detail_page.py -q` | 0 | 38 passed | SC-7 |
| login/logout templates render | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_login_template.py -q` | 0 | 5 passed | SC-8 |
| lint | `cd apps/api && ../../.venv/bin/ruff check app/core/dashboard_auth.py app/core/errors.py app/core/config.py app/core/lifespan.py app/routers/dashboard_login.py app/routers/main.py app/routers/dashboard.py app/routers/dashboard_prompts.py tests/core/test_dashboard_auth.py tests/api/agent_config/test_dashboard_auth.py tests/api/agent_config/test_login_template.py tests/conftest.py` | 0 | All checks passed | SC-9 |
| targeted regression (dashboard + core, superset of the above) | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config tests/api/prompts/test_dashboard_prompts.py tests/core -q` | 0 | 273 passed | |

### Not auto-verified

- "both `/dashboard` routers are the only `/dashboard` routes" — reached traceability (grep of `prefix="/dashboard"` in `app/routers/`); not re-run against the live route table.
- the `lifespan` startup warning fires when `DASHBOARD_BASIC_USER`/`PASSWORD`/`DASHBOARD_SECRET_KEY` is missing — reached traceability (Task 3.2 review confirmed the call site and `ruff check`/`import` pass); not exercised by an automated test, since it requires observing a log line at app startup.
- manual browser verification of the login/logout flow — not run in this session; the developer must add `DASHBOARD_BASIC_USER`, `DASHBOARD_BASIC_PASSWORD`, `DASHBOARD_SECRET_KEY` to `apps/api/.env` first (see Global Constraints in PLAN.md).
- `app/core/errors.py`'s `_handle_http_exception` comment still references "the dashboard guard's `WWW-Authenticate: Basic`" — that guard no longer exists (replaced by the cookie session), but the header-forwarding behaviour it documents is still correct for other 401 raisers (e.g. Supabase auth). Left untouched per the surgical-change rule; design.md flagged it as a known-stale comment.
- `app/routers/dashboard.py:910` and `app/services/booking_service.py:177` also carry stale comments describing the removed HTTP Basic guard — found by intent re-review, outside this feature's file set (Files in `PLAN.md` Global Constraints did not name them); left unfixed to keep this change surgical.

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

None reached the 75 threshold, so none entered the fix loop under correctness-review's own
rules. The `login.html` (score 50) and `login_form` dependency-override (score 25) rows were
independently re-raised by intent-review against the "follow correct fastapi implementation"
clause of the user's request and were fixed there instead — see `### Intent Findings` below,
commit `7d5c9b9`. The trailing-slash `safe_next` and `UnicodeEncodeError` rows (both 25) remain
open advisories; no further action planned.

### Intent Findings

Intent-review (`specs/dashboard-auth-required/SUMMARY.md` → `### Intent`, blind to `PLAN.md`)
ran over the full diff after correctness-review and found 8 divergences, all against the final
user clause "make sure we are following correct authentication concept and implementation from
fastapi. simple but follow correct rule." Routed and closed:

| # | Class | Finding | Route | Outcome |
|---|---|---|---|---|
| 1 | gap | Login form posted to the absolute, `Host`-header-derived `request.url` — no `TrustedHostMiddleware` guards it, so a spoofed `Host` could redirect submitted credentials to a foreign origin | fix | Fixed, commit `7d5c9b9` (relative `action`; test stub updated to a realistic `URL`-shaped object) |
| 2 | drift | `login_form` called `get_current_dashboard_user` as a plain function instead of via `Depends(...)`, so `app.dependency_overrides` couldn't reach the login page | fix | Fixed, commit `7d5c9b9` (`is_already_signed_in` dependency) |
| 3 | drift | `OAuth2PasswordRequestForm` (an OAuth2 token-endpoint class carrying unused `grant_type`/`scope`/`client_id`/`client_secret` fields) is used for a plain HTML login form; FastAPI's documented building block for that is `Form(...)` | advisory | Not changed — `design.md`'s FastAPI-alignment table chose this deliberately and it was approved at design review; behaviorally equivalent (the extra fields are never read). Recorded for a future simplification pass. |
| 4 | drift | `authenticate()` short-circuited `compare_digest(username) and compare_digest(password)`, a timing side-channel revealing username validity | fix | Fixed, commit `7d5c9b9` (both compared unconditionally) |
| 5 | gap | `apps/api/APIS.md` still described the removed HTTP Basic guard (open-in-dev / 404-in-prod) | fix | Fixed, commit `7d5c9b9` |
| 6 | gap (secondary-oracle) | `design.md` promised the stale `WWW-Authenticate: Basic` comment in `errors.py` would be noted in `SUMMARY.md`; it wasn't | fix | Added above under `### Not auto-verified`; comment itself left untouched per the surgical-change rule |
| 7 | excess (dead code) | `dashboard_login.py` passed an unused `"next"` key into every `login.html` template context (the real `next` round-trips via the form's `action` URL) | fix | Fixed, commit `7d5c9b9` (context key removed) |
| 8 | drift (design, not code) | Before this change, production with no dashboard credentials returned 404 (surface hidden); now it renders a "not configured" login page (surface visible, just unusable) | informational | This is decision D1/D4 in `design.md`, explicitly chosen over the fail-fast alternatives and approved by the user during design review. Not re-litigated; flagged here for the record. |

Re-review (fresh intent-reviewer pass, blind to `PLAN.md`, over `0f9d2ed..0de4b53`) confirmed
findings 1, 2, 4, 5, 6, 7 above are genuinely fixed (each re-checked for a concrete trigger of
the original bug; none remained) and found 3 more low-severity issues, all fixed in commit
`bde7aa2`: an unused `next` query parameter left on `GET /dashboard/login` after fix #7
removed its only use; the startup warning wording ("Dashboard login disabled") read as the
opposite of the actual behaviour (locked, not open) — reworded to "Dashboard locked"; and
this paragraph itself, which had asserted a re-review verdict before the re-review ran —
corrected here. Two more stale "Basic auth" comments were found outside this feature's file
set (`app/routers/dashboard.py:910`, `app/services/booking_service.py:177`) and are listed
below alongside the `errors.py` one.

### Rollback

- none yet (intake only). Any implementation: `git revert <sha>`; option A is undone by unsetting the two env vars.

### Harness-Delta

- none
