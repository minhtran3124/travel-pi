# dashboard-auth-required — Design

Status: approved in-session 2026-09-05 (intake `SUMMARY.md`; escalation E001 → option C;
approach 3 chosen over fail-fast variants; four design sections confirmed; revised once after
independent review and once more to align with FastAPI's documented security pattern).

## Purpose

Replace the browser HTTP Basic prompt on `/dashboard/*` with a real login page backed by a
signed session cookie, so an operator must sign in with the single username/password from env
before any dashboard page renders. Auth is always on: with no credentials configured the
dashboard is locked (every page redirects to login, login cannot succeed) and the server warns
at startup instead of refusing to start.

## Problem

`app/core/dashboard_auth.py::require_dashboard_access` (shipped in
`specs/review-a-security-hardening`, E003) gates both dashboard routers with HTTP Basic, opt-in
via `DASHBOARD_BASIC_USER` / `DASHBOARD_BASIC_PASSWORD`. Two things the user wants differ:

1. The browser's Basic dialog is not a login page — no logout, no branded form, no way to see
   "not configured".
2. When the two vars are unset the dashboard is open in development. The user wants
   authentication required in every environment.

## FastAPI alignment (the "correct rule")

The implementation follows the FastAPI security tutorial and reference
(`tutorial/security/oauth2-jwt`, `reference/security`) rather than hand-rolled equivalents:

| Concern | FastAPI-documented building block | Used here |
|---|---|---|
| Collect username/password | `fastapi.security.OAuth2PasswordRequestForm` (form fields `username`, `password`; `python-multipart` already in `requirements.txt`) | `POST /dashboard/login` form dependency |
| Extract the credential from the request | a `fastapi.security` scheme class with `auto_error=False` | `APIKeyCookie(name="dashboard_session", auto_error=False)` |
| Session token | JWT signed with a dedicated secret (`openssl rand -hex 32`), `HS256`, `sub` + `exp` claims, `jwt.encode` / `jwt.decode` from PyJWT | same; PyJWT is already installed and used by `app/core/auth.py` for Supabase tokens |
| Current-user dependency | `get_current_user(token)` that decodes the token and raises on `InvalidTokenError` | `get_current_dashboard_user(cookie) -> DashboardUser` |
| Guarding routes | `Depends(get_current_user)` on the route or router | router-level `dependencies=[Depends(get_current_dashboard_user)]` (unchanged mechanism) |
| Custom failure behaviour | `@app.exception_handler(MyException)` | `DashboardLoginRequired` handler in `errors.py` → 303 for HTML, otherwise the same 401 JSON envelope `AppError` gets |

Deliberate simplifications, and why they do not violate the rule:

- **No password hashing.** The tutorial hashes passwords stored in a database. Here the only
  store is the environment variable itself; hashing a value the process must read in full from
  the same env adds no protection. Comparison stays `secrets.compare_digest` on both fields.
- **No bearer token / `/token` endpoint.** The dashboard is a browser surface; the token lives
  in an `HttpOnly` cookie instead of `Authorization: Bearer`. The JWT itself is identical to the
  tutorial's.
- **No `WWW-Authenticate` header on the 401 path.** Cookie auth has no standard challenge
  scheme (Basic/Bearer do not apply), so none is sent.

## Decisions (WHAT)

| # | Decision | Consequence |
|---|---|---|
| D1 | Auth is always required on `/dashboard/*`; the "open in development" and "404 in production" branches are removed. | Local dev must set the env vars to use the dashboard. Prod without creds no longer hides the surface with 404 — it shows a locked login page (D4). |
| D2 | Session = cookie `dashboard_session` holding an `HS256` JWT with claims `sub=<username>`, `iat`, `exp=iat+12h`, signed with a dedicated secret `DASHBOARD_SECRET_KEY`. Verified with `jwt.decode(token, key, algorithms=["HS256"], leeway=60, options={"require": ["exp", "iat", "sub"]})` (research: without `require`, a token lacking `exp` decodes fine) — PyJWT 2.13 enforces signature, `exp`, a non-future `iat` (`ImmatureSignatureError`) and `sub` being a `str`; no manual timestamp checks. `sub` must equal the configured username. | One **new** env var (generate with `openssl rand -hex 32`). Rotating it logs everyone out; rotating the password does not, because the JWT is bound to `sub`, not the password. No new dependency. |
| D3 | Cookie attributes: `HttpOnly`, `SameSite=Lax`, `Path=/dashboard`, `Secure` iff `settings.is_production`, `max-age` = 12 h to match `exp`. | No sliding renewal, no remember-me. |
| D4 | "Configured" = all three of `DASHBOARD_BASIC_USER`, `DASHBOARD_BASIC_PASSWORD`, `DASHBOARD_SECRET_KEY` non-empty **and** the secret at least 32 bytes (PyJWT 2.13 warns `InsecureKeyLengthWarning` below that; `openssl rand -hex 32` gives 64). Missing any → guard still redirects; `lifespan` logs a `warning` at startup naming the missing vars; the login page renders "Dashboard login is not configured on this server"; `POST /login` answers 401. | Server keeps running (no fail-fast); the dashboard is unusable until env is set. |
| D5 | `get_current_dashboard_user` raises `DashboardLoginRequired` (subclass of the existing `AuthError`, status 401). Its handler is declared **inside** `register_exception_handlers` in `app/core/errors.py` (next to `_handle_app_error`, so it can reuse the private `_error_body`/handler closure): when the request accepts `text/html` it returns `303 → /dashboard/login?next=<path+query>` without logging; otherwise it returns `await _handle_app_error(request, exc)`, the existing 401 JSON envelope (what `/dashboard/_search.json`, fetched with `Accept: */*`, receives). Starlette picks the most specific MRO match and never falls through, so the handler must produce both responses itself — it never re-raises. | No change to the JSON error contract; no new public surface in `dashboard_auth.py` for this. |
| D6 | `next` is honoured only when it starts with `/dashboard`, contains no `\r`/`\n`, and is not `/dashboard/login`; otherwise `/dashboard`. `startswith("/dashboard")` already rejects `//host`; never loosen to `/`. | Closes open-redirect. |
| D7 | Existing setting names `dashboard_basic_user` / `dashboard_basic_password` are kept (env unchanged); `dashboard_secret_key` is added. Comments and `.env.example` updated. | Minimal env churn: one added var. |
| D8 | Login/logout live on a new router `app/routers/dashboard_login.py` (prefix `/dashboard`, **no** guard dependency) registered in `routers/main.py` next to the two dashboard routers. | The router-level guard on `dashboard.py` / `dashboard_prompts.py` only changes its target name. |
| D9 | The shared session-scoped `client` fixture in `tests/conftest.py` overrides `get_current_dashboard_user` with a stub returning `DashboardUser("test-ops")` via `app.dependency_overrides`, exactly as it already overrides `get_current_user`. | The six dashboard page-test modules that use `client` (`test_agent_config_dashboard.py`, `test_dashboard_prompts.py`, `test_dashboard_language.py`, `test_tips.py`, `test_visa.py`, `test_places.py`) stay untouched. |
| D10 | Every settings read for this feature goes through `app.core.dashboard_auth` (`get_settings` imported there); `dashboard_login.py` calls its public helpers and never imports `get_settings` itself. | The existing test seam — `monkeypatch.setattr("app.core.dashboard_auth.get_settings", ...)` — controls guard, login and logout alike. |
| D11 | `GET /dashboard/login` with a valid session redirects `303` to `/dashboard`. | No "already signed in" form state. |

## Out of scope (non-goals)

- Rate-limiting / lockout on `POST /login`.
- CSRF token on the login/logout forms (`SameSite=Lax` is the only mitigation).
- Password hashing of the env value, multiple operator users, roles, remember-me, sliding
  sessions, refresh tokens.
- Renaming the two existing env vars.
- Fail-fast on missing credentials (approaches 1–2, rejected by the user).

## Shape of the change (HOW)

### Components

- **`app/core/dashboard_auth.py`** (rewrite):
  - `SESSION_COOKIE = "dashboard_session"`, `SESSION_TTL = timedelta(hours=12)`,
    `LOGIN_PATH = "/dashboard/login"`, `_ALGORITHM = "HS256"`.
  - `_cookie_scheme = APIKeyCookie(name=SESSION_COOKIE, scheme_name="dashboardSession",
    auto_error=False)` — it will appear as an unused scheme under `/docs` `securitySchemes`;
    harmless.
  - `@dataclass(frozen=True) class DashboardUser: username: str` — mirrors `AuthUser`.
  - `class DashboardLoginRequired(AuthError)` — raised by the dependency; carries nothing else.
  - `credentials_configured() -> bool` and `missing_credentials() -> list[str]` (for the
    startup warning).
  - `authenticate(username, password) -> bool` — `secrets.compare_digest` on both;
    `TypeError` → `False`.
  - `create_session_token(username, now=None) -> str` — `jwt.encode({"sub", "iat", "exp"},
    settings.dashboard_secret_key, algorithm="HS256")`.
  - `get_current_dashboard_user(token: Annotated[str | None, Depends(_cookie_scheme)]) ->
    DashboardUser` — `None` token, unconfigured credentials, `jwt.InvalidTokenError`
    (covers bad signature, expired, malformed, `alg` mismatch), or `sub != configured user` →
    raise `DashboardLoginRequired`. This is the router-level guard.
  - `safe_next(value) -> str` (D6) and `login_redirect_url(request) -> str`.
  - `set_session_cookie(response, token)` / `clear_session_cookie(response)` — D3 attributes;
    `delete_cookie` repeats `path="/dashboard"` and the same flags, or browsers keep the cookie.
- **`app/routers/dashboard_login.py`** (new):
  - `GET /login?next=` → `303 /dashboard` when the cookie already verifies (D11); otherwise
    `login.html` with `next`, `error`, `configured` (200).
  - `POST /login?next=` with `form: Annotated[OAuth2PasswordRequestForm, Depends()]` → on
    `authenticate()` success: `create_session_token`, `set_session_cookie`, `303 safe_next(next)`;
    on failure or unconfigured: re-render the form, status 401, no cookie. The form's `action`
    is the current URL so `?next=` round-trips as a query parameter, not a hidden field.
  - `POST /logout` → `clear_session_cookie`, `303 /dashboard/login`.
- **`app/templates/login.html`** (new): standalone page (no sidebar); reuses the colour tokens
  from `base.html`'s `:root`; one card with username, password, submit, error line,
  not-configured notice.
- **`app/templates/base.html`**: `<form method="post" action="/dashboard/logout">` button in
  `.app-topbar` next to the "API Docs" link.
- **`app/core/lifespan.py`**: `logger.warning("Dashboard login disabled: missing %s", ...)`
  when `credentials_configured()` is `False`.
- **`app/core/errors.py`**: add `@app.exception_handler(DashboardLoginRequired)` inside
  `register_exception_handlers` (D5). Imports `DashboardLoginRequired`, `login_redirect_url`
  from `app.core.dashboard_auth` (no circular import: `dashboard_auth` imports from
  `app.exceptions` and `app.core.config` only).
- **`app/core/config.py`**: add `dashboard_secret_key: str | None = None`; update the comment
  block. **`.env.example`**: document all three vars and the `openssl rand -hex 32` command.
- **`app/routers/main.py`**: `router.include_router(dashboard_login.router)`.
- **`app/routers/dashboard.py`, `dashboard_prompts.py`**: `Depends(require_dashboard_access)`
  → `Depends(get_current_dashboard_user)`.
- **`tests/conftest.py`**: dependency override (D9).

### Data flow

```
GET /dashboard/prompts (no cookie, Accept: text/html)
  → get_current_dashboard_user raises DashboardLoginRequired
  → handler: 303 /dashboard/login?next=/dashboard/prompts
GET /dashboard/login?next=/dashboard/prompts → form
POST /dashboard/login?next=/dashboard/prompts (username, password)
  → authenticate() → jwt.encode({sub, iat, exp}) → Set-Cookie dashboard_session=<jwt>
  → 303 /dashboard/prompts
GET /dashboard/prompts (cookie) → jwt.decode ok, sub matches → page
POST /dashboard/logout → Set-Cookie (expired) → 303 /dashboard/login
```

### Error behaviour

| Situation | Response |
|---|---|
| No / malformed / forged / expired cookie, HTML request | 303 → `/dashboard/login?next=<path+query>` |
| Same, non-HTML request | `DashboardLoginRequired` handler, non-HTML branch → 401 JSON envelope |
| Wrong username or password | 401, `login.html` with "Invalid username or password" |
| Credentials not configured (any of the three vars) | pages redirect as above; login page shows the not-configured notice; `POST /login` → 401 with the same notice; startup `warning` |
| `next` not under `/dashboard`, equal to `/dashboard/login`, or containing CR/LF | ignored, redirect to `/dashboard` |
| `POST /dashboard/agent-config/{name}` with an expired session | 303 to login with `next=` that path; after login the browser GETs it, so the form body is dropped and the operator re-submits. Accepted; not a bug. |
| `POST /login` missing `username` or `password` field (hand-crafted request) | FastAPI's `RequestValidationError` → existing 422 JSON envelope; the HTML form marks both inputs `required` so browsers never send this. Accepted. |
| Non-ASCII input to `compare_digest` | caught (`TypeError`) → wrong credentials, never 500 (kept from the current guard) |
| Token signed with the wrong key, `alg=none`, or a Supabase RS256 token pasted into the cookie | `jwt.InvalidTokenError` (algorithms pinned to `["HS256"]`) → treated as no cookie |

### Tests

Three existing modules encode the branches D1 removes and must change:

- `tests/api/agent_config/test_dashboard_auth.py` — rewrite to the cases below.
- `tests/api/agent_config/test_agent_runs_dashboard.py` and
  `tests/api/agent_config/test_agent_run_detail_page.py` — each builds its own client per
  `Settings` and asserts "development + no creds → 200" and "production + no creds → 404".
  Replace those with: configured creds + logged-in cookie → 200; no cookie → 303. Their
  page-content assertions stay.

`tests/api/agent_config/test_dashboard_auth.py` cases (build-a-client-per-`Settings` pattern;
everything reads `app.core.dashboard_auth.get_settings`, D10; fixtures use a 64-hex-char
secret so PyJWT does not warn):

1. creds unset (each of the three vars missing in turn, plus a 10-byte secret, asserting under
   `warnings.simplefilter("error")` that no `InsecureKeyLengthWarning` is raised) → `GET /dashboard` 303 to login;
   `POST /login` 401 with the not-configured notice; `GET /login` 200 shows the notice.
2. creds set, no cookie → 303 with `next=/dashboard/prompts`; `GET /dashboard/_search.json`
   with `Accept: application/json` → 401 JSON envelope.
3. correct login → 303 + `Set-Cookie` (HttpOnly, SameSite=Lax, Path=/dashboard, Max-Age);
   following `GET /dashboard` and `GET /dashboard/prompts` → 200.
4. wrong password / wrong username → 401, no `Set-Cookie`.
5. cookie signed with a different key, expired token (freeze time past `exp`), token with
   `sub` ≠ configured user → 303 to login.
6. `next=https://evil.example`, `next=//evil.example`, `next=/docs`, `next=/dashboard/login`
   → 303 to `/dashboard`; `next=/dashboard/places?city=Da+Nang` → preserved.
7. logout → cookie cleared; next `GET /dashboard` → 303.
8. `Secure` present iff `environment=production`.
9. `GET /dashboard/login` with a valid cookie → 303 `/dashboard`.
10. malformed cookie values (`"abc"`, `"a.b"`, a Supabase-shaped RS256 token) → 303.

Verify: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config -q` and the full
`make test` (SQLite). Nine test files reference `/dashboard` (grep at design time): six use the
shared `client` fixture (covered by D9), three are the per-`Settings` modules above.

## Risks

- **Behaviour change in prod without creds**: 404 → locked login page. Deliberate (D1/D4);
  called out in `.env.example`.
- **One new env var**: `DASHBOARD_SECRET_KEY` must be set alongside the existing two in every
  environment (local `.env`, Docker `env_file`, any deploy). Mitigated by the startup warning
  naming the missing vars and the not-configured notice.
- **`_search.json` from the palette**: `base.html` calls it with `fetch()`, which sends
  `Accept: */*`, so D5 yields 401 JSON, not a redirect. Covered by test 2.
- **This checkout**: `apps/api/.env` has no `DASHBOARD_*` entries. The PLAN must include a
  manual step to add the three vars to the developer's `.env` (never committed) before
  verifying in the browser.
- **Known-stale comment**: `app/core/errors.py` lines ~121–123 mention the old guard's
  `WWW-Authenticate: Basic`; left alone per the surgical-change rule, noted in SUMMARY.
