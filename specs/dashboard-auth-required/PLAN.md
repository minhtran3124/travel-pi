---
slug: dashboard-auth-required
status: active
owner: Minh Tran
created: 2026-09-05
---

# dashboard-auth-required — Login page + JWT cookie session for `/dashboard/*`

**Base:** `main`. **Branch:** `feat/dashboard-auth-required`. Design: `design.md` (D1–D11).
Research: `research-brief.md` (Deep). Lane: `high-risk` (auth hard gate) — see `SUMMARY.md`.

## Global Constraints

- Implement exactly the decisions D1–D11 in `design.md`; no password hashing, no rate-limit,
  no CSRF token, no env-var rename (non-goals).
- No new dependency. Use `fastapi.security.APIKeyCookie`, `OAuth2PasswordRequestForm`, and
  `jwt` (PyJWT 2.13, already installed). `jwt.decode` MUST pass `algorithms=["HS256"]`,
  `leeway=60`, and `options={"require": ["exp", "iat", "sub"]}`.
- Every settings read for this feature goes through `app.core.dashboard_auth.get_settings`
  (D10); `dashboard_login.py` and `errors.py` never import `get_settings` for it.
- The `DashboardLoginRequired` handler lives inside `register_exception_handlers` in
  `app/core/errors.py` and returns either the 303 or `await _handle_app_error(request, exc)`;
  it never re-raises (research: re-raise → 500).
- `delete_cookie` repeats `path="/dashboard"` and the same `httponly`/`samesite`/`secure` flags
  as `set_cookie`.
- Test fixtures use a 64-hex-char `dashboard_secret_key`; the unconfigured cases assert under
  `warnings.simplefilter("error")` that no `InsecureKeyLengthWarning` is raised.
- Backend commands run from `apps/api/` with `../../.venv/bin/python`. Every `Verify` and SC
  check is a single pipe-free command under 60s; the full suite (`make test`, then
  `make test-docker`) runs at `finishing-a-development-branch`.
- Write import + first usage in the same edit (ruff-on-edit strips unused imports).
- Stage and commit as separate commands; no Claude attribution trailers (`CLAUDE.local.md`).
- Same-wave tasks share no files.
- The stale `WWW-Authenticate: Basic` comment in `app/core/errors.py` (~lines 121–123) is left
  untouched (surgical-change rule) and recorded in `SUMMARY.md` → Not auto-verified by Task 2.1.
- Manual, never committed: before browser verification add `DASHBOARD_BASIC_USER`,
  `DASHBOARD_BASIC_PASSWORD`, `DASHBOARD_SECRET_KEY` (`openssl rand -hex 32`) to `apps/api/.env`.

## 1. Motivation

See `design.md` → Problem. The dashboard guard is opt-in HTTP Basic that is open in development;
the user wants a real login page and authentication required in every environment.

## 2. Non-goals

Rate-limiting on login, CSRF tokens, password hashing of the env value, multiple users, remember-me,
renaming the existing env vars, fail-fast on missing credentials.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | Token helpers: a token issued for the configured user verifies; wrong key, expired, future-`iat`, missing `exp`, `sub` mismatch, malformed strings all fail; `safe_next` accepts only `/dashboard…` paths without CR/LF and not `/dashboard/login`; `credentials_configured` is false when any var is missing or the secret is shorter than 32 bytes | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_dashboard_auth.py -q` | exit 0 |
| SC-2 | Without a valid cookie an HTML request to any `/dashboard/*` page answers 303 to `/dashboard/login?next=<path+query>`, and a non-HTML request (`/dashboard/_search.json`) answers 401 with the JSON envelope | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q -k test_unauth` | exit 0 |
| SC-3 | `POST /dashboard/login` with the configured username/password sets `dashboard_session` (HttpOnly, SameSite=Lax, Path=/dashboard, Max-Age) and 303s to the sanitised `next`; the cookie then unlocks `/dashboard` and `/dashboard/prompts`; `GET /dashboard/login` with a valid cookie 303s to `/dashboard` | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q -k test_login` | exit 0 |
| SC-4 | Wrong credentials answer 401 with the re-rendered form and no `Set-Cookie`; forged, expired, `sub`-mismatched and malformed cookies answer 303 to login; open-redirect `next` values collapse to `/dashboard` while a `/dashboard/places?city=…` `next` is preserved | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q -k "test_reject or test_next"` | exit 0 |
| SC-5 | With any of the three vars missing (or a 10-byte secret) every page 303s to login, `GET /dashboard/login` shows "Dashboard login is not configured on this server", `POST /dashboard/login` answers 401, and no `InsecureKeyLengthWarning` is emitted | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q -k test_unconfigured` | exit 0 |
| SC-6 | `POST /dashboard/logout` clears the cookie and the next `/dashboard` request 303s to login; `Secure` is present on the cookie only when `environment=production` | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q -k "test_logout or test_secure"` | exit 0 |
| SC-7 | Existing dashboard page tests that use the shared `client` fixture still render 200 through the dependency override, and the per-`Settings` agent-runs pages render 200 with a session cookie and 303 without | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py tests/api/prompts/test_dashboard_prompts.py tests/api/agent_config/test_agent_runs_dashboard.py tests/api/agent_config/test_agent_run_detail_page.py -q` | exit 0 |
| SC-8 | `login.html` and the modified `base.html` compile as Jinja templates and `login.html` contains the `username`, `password` inputs and a `POST` form; `base.html` contains a `POST /dashboard/logout` form | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_login_template.py -q` | exit 0 |
| SC-9 | All changed Python files pass ruff lint and format checks | `cd apps/api && ../../.venv/bin/ruff check app/core/dashboard_auth.py app/core/errors.py app/core/config.py app/core/lifespan.py app/routers/dashboard_login.py app/routers/main.py app/routers/dashboard.py app/routers/dashboard_prompts.py tests/core/test_dashboard_auth.py tests/api/agent_config/test_dashboard_auth.py tests/api/agent_config/test_login_template.py tests/conftest.py` | exit 0 |

## 4. Tasks

### Task 1.1 — Core session module + setting + unit tests (wave 1)

- **Files:** apps/api/app/core/dashboard_auth.py, apps/api/app/core/config.py, apps/api/app/routers/dashboard.py, apps/api/app/routers/dashboard_prompts.py, apps/api/tests/core/test_dashboard_auth.py
- **Action:** Write the unit tests first (`tests/core/test_dashboard_auth.py`, monkeypatching
  `app.core.dashboard_auth.get_settings` with `Settings(dashboard_basic_user=..., dashboard_basic_password=..., dashboard_secret_key="a"*64)`),
  then rewrite `app/core/dashboard_auth.py` per `design.md` → Components: constants
  `SESSION_COOKIE`, `SESSION_TTL`, `LOGIN_PATH`, `_ALGORITHM`; `_cookie_scheme = APIKeyCookie(name=SESSION_COOKIE, scheme_name="dashboardSession", auto_error=False)`;
  `DashboardUser` frozen dataclass; `class DashboardLoginRequired(AuthError)`;
  `credentials_configured()`, `missing_credentials() -> list[str]` (names of unset vars, plus
  `"DASHBOARD_SECRET_KEY"` when shorter than 32 bytes); `authenticate(username, password)`
  (`secrets.compare_digest` both, `TypeError` → `False`); `create_session_token(username, now=None)`
  (`jwt.encode({"sub", "iat", "exp"}, secret, algorithm="HS256")`);
  `get_current_dashboard_user(token: Annotated[str | None, Depends(_cookie_scheme)]) -> DashboardUser`
  raising `DashboardLoginRequired` on `None`, unconfigured, `jwt.InvalidTokenError`, or `sub` ≠ user;
  `safe_next(value)`; `login_redirect_url(request)` (path + query preserved, URL-encoded);
  `set_session_cookie(response, token)` / `clear_session_cookie(response)` with the D3 flags and
  `secure=get_settings().is_production`. Delete the HTTP Basic code. In the same task swap the
  router-level dependency in `app/routers/dashboard.py` and `dashboard_prompts.py` from
  `require_dashboard_access` to `get_current_dashboard_user` (import + `dependencies=[...]`), so
  `app.main` stays importable at the wave-1 boundary (the root `tests/conftest.py` imports it
  during collection). Add
  `dashboard_secret_key: str | None = None` to `Settings` and replace the comment block at
  `config.py:200-206` with the D1/D2/D4 description. Unit tests cover every SC-1 clause and
  assert `warnings.simplefilter("error")` raises nothing for the short-secret case.
- **Criteria:** SC-1
- **Interfaces:** Consumes: the existing Settings class, the existing AuthError, PyJWT and FastAPI's APIKeyCookie (external, already present). Produces: `apps/api/app/core/dashboard_auth.py` (public names above), `apps/api/app/core/config.py` (`dashboard_secret_key`), `apps/api/app/routers/dashboard.py`, `apps/api/app/routers/dashboard_prompts.py` (guard swapped), `apps/api/tests/core/test_dashboard_auth.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_dashboard_auth.py -q`
- **Done:** SC-1 file passes; `ruff check app/core/dashboard_auth.py app/core/config.py app/routers/dashboard.py app/routers/dashboard_prompts.py` exits 0; `grep -c require_dashboard_access app/core/dashboard_auth.py app/routers/dashboard.py app/routers/dashboard_prompts.py` reports 0 for all three; `python -c "import app.main"` exits 0.

### Task 1.2 — Login template + logout button (wave 1)

- **Files:** apps/api/app/templates/login.html, apps/api/app/templates/base.html, apps/api/tests/api/agent_config/test_login_template.py
- **Action:** Write `tests/api/agent_config/test_login_template.py` first: it builds
  `Jinja2Templates(directory=<app/templates>)`, renders `login.html` with
  `{"request": <a Starlette Request built from a scope>, "next": "/dashboard", "error": None, "configured": True}`
  (render via `templates.get_template("login.html").render(...)` with a stub `request` object
  exposing `.url`, not a hand-written ASGI scope) and with `configured=False`, and asserts the rendered HTML contains `name="username"`,
  `name="password"`, `method="post"`, and (unconfigured case) the exact string
  `Dashboard login is not configured on this server`; it also asserts `base.html` source
  contains `action="/dashboard/logout"` and `method="post"`. Then create `login.html` as a
  standalone page (no `{% extends %}`): copy only the `:root` colour tokens block from
  `base.html` into its own `<style>`, one centred card with `<form method="post" action="{{ request.url }}">`,
  `<input name="username" required autocomplete="username">`,
  `<input type="password" name="password" required autocomplete="current-password">`, an error
  line rendered when `error` is set, the not-configured notice rendered when `configured` is
  false (submit button disabled in that case). Add to `base.html` `.app-topbar`, after the
  "API Docs" link, `<form method="post" action="/dashboard/logout" class="logout-form"><button type="submit" class="tab">Log out</button></form>`.
- **Criteria:** SC-8
- **Interfaces:** Consumes: the existing base.html colour tokens (external, already present). Produces: `apps/api/app/templates/login.html`, `apps/api/app/templates/base.html` (logout form), `apps/api/tests/api/agent_config/test_login_template.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_login_template.py -q`
- **Done:** SC-8 file passes; `login.html` has no `{% extends %}`; `base.html` diff is limited to the topbar form.

### Task 2.1 — Redirect handler + shared test seam (wave 2)

- **Files:** apps/api/app/core/errors.py, apps/api/tests/conftest.py, apps/api/tests/api/agent_config/test_agent_runs_dashboard.py, apps/api/tests/api/agent_config/test_agent_run_detail_page.py
- **Action:** In `errors.py::register_exception_handlers`, after `_handle_app_error`, add
  `@app.exception_handler(DashboardLoginRequired)` that returns
  `RedirectResponse(login_redirect_url(request), status_code=303)` when `"text/html"` is in the
  `Accept` header (no log line), else `return await _handle_app_error(request, exc)`. In
  `tests/conftest.py::client` add
  `app.dependency_overrides[get_current_dashboard_user] = lambda: DashboardUser(username="test-ops")`
  next to the `get_current_user` override, with a comment mirroring the #118 one. In the two
  per-`Settings` test modules: give `_build_client` a configured `Settings` (user/password +
  64-hex secret) and a helper that sets `client.cookies[SESSION_COOKIE] = create_session_token(user)`;
  rewrite `*_renders_in_dev` tests to log in via that helper and keep their content assertions;
  replace each `*_404_in_production_without_credentials` test with a `*_redirects_without_cookie`
  test asserting 303 and a `Location` starting with `/dashboard/login?next=`. The stale
  `tests/api/agent_config/test_dashboard_auth.py` is expected to be red until Task 3.1 — it is
  excluded from this task's Verify by `--ignore`.
- **Criteria:** SC-7
- **Interfaces:** Consumes: `apps/api/app/core/dashboard_auth.py` (get_current_dashboard_user, DashboardUser, DashboardLoginRequired, login_redirect_url, create_session_token, SESSION_COOKIE) and the swapped `apps/api/app/routers/dashboard.py` from Task 1.1. Produces: `apps/api/app/core/errors.py` (handler), `apps/api/tests/conftest.py` (override), `apps/api/tests/api/agent_config/test_agent_runs_dashboard.py`, `apps/api/tests/api/agent_config/test_agent_run_detail_page.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config tests/api/prompts/test_dashboard_prompts.py -q --ignore=tests/api/agent_config/test_dashboard_auth.py`
- **Done:** every listed test passes; `grep -c DashboardLoginRequired app/core/errors.py` reports at least 2 (import + handler); `grep -c get_current_dashboard_user tests/conftest.py` reports at least 1.

### Task 2.2 — Login/logout router (wave 2)

- **Files:** apps/api/app/routers/dashboard_login.py, apps/api/app/routers/main.py
- **Action:** Create `app/routers/dashboard_login.py` with `router = APIRouter(prefix="/dashboard", tags=[Tags.dashboard], include_in_schema=False)`
  (no guard dependency) and `_TEMPLATES` resolved like `dashboard.py`. Routes:
  `GET /login` (`next: str = "/dashboard"`, `token: Annotated[str | None, Depends(_cookie_scheme)]`):
  if the token verifies via a `try: get_current_dashboard_user(token) except DashboardLoginRequired`
  → `RedirectResponse("/dashboard", 303)`; else `TemplateResponse("login.html", {"request", "next": safe_next(next), "error": None, "configured": credentials_configured()})`.
  `POST /login` (`next: str = "/dashboard"`, `form: Annotated[OAuth2PasswordRequestForm, Depends()]`):
  if not `credentials_configured()` → render with the not-configured notice, status 401; elif
  `authenticate(form.username, form.password)` → `RedirectResponse(safe_next(next), 303)` with
  `set_session_cookie(response, create_session_token(form.username))`; else render with
  `error="Invalid username or password"`, status 401, no cookie. `POST /logout` →
  `RedirectResponse(LOGIN_PATH, 303)` + `clear_session_cookie`. Register in `routers/main.py`
  after `dashboard_prompts.router`. Reads settings only through `dashboard_auth` helpers (D10).
- **Criteria:** SC-3
- **Interfaces:** Consumes: `apps/api/app/templates/login.html` (Task 1.2); `apps/api/app/core/dashboard_auth.py` (_cookie_scheme, get_current_dashboard_user, DashboardLoginRequired, credentials_configured, authenticate, create_session_token, safe_next, set_session_cookie, clear_session_cookie, LOGIN_PATH) from Task 1.1. Produces: `apps/api/app/routers/dashboard_login.py` (routes `GET/POST /dashboard/login`, `POST /dashboard/logout`), `apps/api/app/routers/main.py` (registration).
- **Verify:** `cd apps/api && ../../.venv/bin/python -c "from app.main import app; paths={(r.path, m) for r in app.routes if hasattr(r, 'methods') for m in r.methods}; assert ('/dashboard/login','GET') in paths and ('/dashboard/login','POST') in paths and ('/dashboard/logout','POST') in paths, paths"`
- **Done:** the three routes exist; `ruff check app/routers/dashboard_login.py app/routers/main.py` exits 0; the module contains no `get_settings` import.

### Task 3.1 — Rewrite the guard behaviour tests (wave 3)

- **Files:** apps/api/tests/api/agent_config/test_dashboard_auth.py
- **Action:** Replace the four-state Basic tests with the ten cases in `design.md` → Tests,
  keeping the `_build_client(tmp_db, monkeypatch, settings)` pattern (monkeypatch
  `app.core.dashboard_auth.get_settings` and `app.main.get_settings`; use `TestClient(app)`
  without lifespan). Name tests by prefix so SC `-k` selectors resolve: `test_unauth_*` (SC-2),
  `test_login_*` (SC-3, incl. `test_login_page_redirects_when_already_signed_in`),
  `test_reject_*` and `test_next_*` (SC-4), `test_unconfigured_*` (SC-5, parametrised over the
  three missing vars and a 10-byte secret, wrapped in `warnings.catch_warnings()` +
  `simplefilter("error")`), `test_logout_*` and `test_secure_*` (SC-6, production `Settings`
  needs `cors_origins=["https://app.example.com"]`). Use `follow_redirects=False` on every
  request that asserts a 303. Expired/forged tokens are built with `jwt.encode` directly.
- **Criteria:** SC-2, SC-3, SC-4, SC-5, SC-6
- **Interfaces:** Consumes: `apps/api/app/routers/dashboard_login.py` (Task 2.2), `apps/api/app/core/errors.py` and `apps/api/tests/conftest.py` (Task 2.1), `apps/api/app/core/dashboard_auth.py` (Task 1.1). Produces: `apps/api/tests/api/agent_config/test_dashboard_auth.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_dashboard_auth.py -q`
- **Done:** all ten cases pass; each SC-2…SC-6 `-k` selector collects at least one test (`--collect-only -q` shows a non-zero count); no test name starts with `test_login_required` or any other prefix that would let an SC-2 case match `-k test_login`.

### Task 3.2 — Startup warning + env docs (wave 3)

- **Files:** apps/api/app/core/lifespan.py, apps/api/.env.example
- **Action:** In `lifespan`, right after the `Database URL` log line, add
  `missing = missing_credentials()` and, when non-empty,
  `logger.warning("Dashboard login disabled: set %s to enable /dashboard", ", ".join(missing))`.
  Replace the `.env.example` dashboard block (lines ~110–116) with the three vars, the
  `openssl rand -hex 32` hint, and the D1/D4 behaviour (always required; locked with a notice
  when any var is missing; no longer 404 in production).
- **Criteria:** SC-9
- **Interfaces:** Consumes: `apps/api/app/core/dashboard_auth.py` (missing_credentials) from Task 1.1. Produces: `apps/api/app/core/lifespan.py` (warning), `apps/api/.env.example` (three documented vars).
- **Verify:** `cd apps/api && ../../.venv/bin/ruff check app/core/lifespan.py && ../../.venv/bin/python -c "import app.core.lifespan"`
- **Done:** ruff and import succeed; `.env.example` lists `DASHBOARD_SECRET_KEY`; the warning text is recorded in `SUMMARY.md` → Not auto-verified (lifespan is not exercised by a unit test).

## 5. Risks

- Transient red between waves (planned, not a regression): after wave 1 the six shared-`client`
  dashboard modules and the two per-`Settings` modules fail until Task 2.1 lands the override
  and rewrites; after wave 2 `test_dashboard_auth.py` stays red until Task 3.1. No wave Verify
  runs those files before their fixing task.
- `_search.json` `Accept` detection is inferred (`fetch` → `*/*`); covered by SC-2's JSON case.
- Docker image is Python 3.12 vs local 3.14 — no version-specific syntax is used; `make test-docker`
  runs at finishing.
- The startup warning has no automated proof (Task 3.2); it is listed under Not auto-verified.
- SC-7 samples two of the six shared-`client` dashboard modules (`test_dashboard_language.py`,
  `test_tips.py`, `test_visa.py`, `test_places.py` are not in the row); the full suite at
  `finishing-a-development-branch` covers the rest.
- Task 2.1 Verify measured ~37s wall on the current tree; if it nears 60s, move
  `tests/api/prompts/test_dashboard_prompts.py` into its own row.

## 6. Status Log

- 2026-09-05 — plan written (proposed).
- 2026-09-05 — tasks 1.1, 1.2 complete; commits 10dc7a1, c35f01e; review fixes 49bdc2a.
  Task 1.1 spec pass / quality approved (2 Minor, both fixed). Task 1.2 spec pass /
  quality needs_fixes (invalid `font:` shorthand) — fixed in 49bdc2a and re-verified.
- 2026-09-05 — tasks 2.1, 2.2 complete; commits d790739, 687bb98. Both spec pass /
  quality approved, zero findings.
