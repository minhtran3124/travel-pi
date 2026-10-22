# dashboard-auth-required — Research Brief

Depth: **Deep** (intake lane `high-risk`, hard gate `auth`; not reclassified). External surface:
**yes** — relies on version-specific APIs of FastAPI 0.136 / Starlette 1.2 / PyJWT 2.13, though
it adds no dependency. Waiver: none.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **use built-in** — FastAPI `APIKeyCookie` + `OAuth2PasswordRequestForm` + PyJWT HS256, shaped after fastapi-users' `CookieTransport`/`JWTStrategy` split without taking the dependency |
| **Why this is the lightest credible path** | every building block is already installed and already used in this repo (PyJWT in `app/core/auth.py`, `python-multipart` for dashboard forms, `AppError` handler in `errors.py`); the change is one module rewrite, one small router, one template, one setting |
| **Confidence** | 90% |
| **Next step** | `writing-plans` — the design is approved; two facts below must land in the plan verbatim: `jwt.decode(..., options={"require": ["exp", "iat", "sub"]})` and the handler placement inside `register_exception_handlers` |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | monorepo (pnpm + Turborepo); this change is API-only (`apps/api`) |
| Primary language + runtime | Python — local venv 3.14, Docker image `python:3.12-slim`, `requires-python >= 3.10` |
| Frameworks / platforms | FastAPI 0.136.3, Starlette 1.2.1 (pinned `<1.3` — route-introspection break), Pydantic 2.13.4, Jinja2 templates |
| Relevant packages | `pyjwt` 2.13.0 (`>=2.8,<3`), `python-multipart` (`>=0.0.7`), `cryptography` (unused by HS256) |
| Detectable versions | `apps/api/requirements.txt`, venv introspection |
| Important constraints | `rules/behavior.md` (surgical, no speculative abstraction); `.claude/harness-manifest.json` `auth` gate is block-mode → Lane must stay `high-risk`; commit-quality-gate needs `### Verify` rows; ruff-on-edit strips imports added before use |

---

## Feature Understanding and Assumptions

- **Requested feature:** "plan to add simple authentication (username/pass) for the dashboard.
  Require authen when access the dashboard page." → refined in-session to option C (login page +
  cookie session), approach 3 (always required, locked-not-fail-fast when unconfigured), and
  "follow correct FastAPI authentication concept and implementation, simple".
- **What success appears to mean:** any `/dashboard/*` GET without a valid session lands on
  `/dashboard/login`; correct env credentials produce a cookie that unlocks every page; logout
  works; `make test` green; no new dependency.
- **Assumptions from the request:** single operator identity from env; browser is the only
  client; the JSON helper `/dashboard/_search.json` keeps its 401 JSON contract.
- **Assumptions still needing confirmation:** none blocking. The user has not yet been told
  that `jwt.decode` needs an explicit `require` list (finding below) — it is an implementation
  detail that strengthens D2, not a design change.

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `app/core/dashboard_auth.py` is a 70-line Basic guard attached at router level in `app/routers/dashboard.py:69-74` and `dashboard_prompts.py:26-31`; those are the only `/dashboard` routers (`routers/main.py:55-56`). |
| `Local` | `app/core/auth.py` already does `import jwt`, `jwt.decode(..., algorithms=[...])`, raises `AuthError`, returns a frozen `AuthUser` dataclass — the exact shape `DashboardUser`/`get_current_dashboard_user` should mirror. |
| `Local` | `app/core/errors.py::register_exception_handlers` owns `_handle_app_error` (closure) and `_error_body` (module-private). A handler that wants the 401 envelope must live in that function. |
| `Local` | `tests/conftest.py::client` (session-scoped) already overrides `get_current_user` via `app.dependency_overrides` → same seam for `get_current_dashboard_user` (D9). Nine test files reference `/dashboard`; six use `client`, three build per-`Settings` clients. |
| `Local` | `tests/api/agent_config/test_agent_runs_dashboard.py:85-105` and `test_agent_run_detail_page.py:133-173` assert "dev open / prod 404" — the branches D1 deletes. |
| `Local` | `.github/workflows/*.yml` set no `DASHBOARD_*` vars; `docker-compose.yml` `api` uses `env_file: .env`; `apps/api/.env` has no `DASHBOARD_*` today. Approach 3 (no fail-fast) means none of these break. |
| `Local` (empirical) | Starlette 1.2.1 handler lookup walks `type(exc).__mro__` (`starlette/_exception_handler.py`); a `Child` handler beats a `Base` handler; a handler that re-raises reaches the `Exception` catch-all → **500**. A `Child` handler that `return await base_handler(...)` yields the base JSON. Verified with a throwaway app in the venv. |
| `Local` (empirical) | PyJWT 2.13: `jwt.encode(..., "short", "HS256")` raises `InsecureKeyLengthWarning` under `warnings.simplefilter("error")`; future `iat` → `ImmatureSignatureError`; **a token without `exp` decodes successfully** unless `options={"require": [...]}` is passed (`MissingRequiredClaimError` then). |
| `Local` (empirical) | `fastapi.security.APIKeyCookie.__init__(*, name, scheme_name=None, description=None, auto_error=True)`; with `auto_error=False` the dependency returns `None` when the cookie is absent. |
| `Upstream` | fastapi-users splits transport (`CookieTransport`: name, max_age, path, secure=True, httponly=True, samesite="lax") from strategy (`JWTStrategy(secret, lifetime_seconds)`); logout = `POST` that deletes the cookie. Our design is the same split in one module without the library. |
| `Docs` | FastAPI `tutorial/security/oauth2-jwt`: `OAuth2PasswordRequestForm` via `Depends()`, `jwt.encode({"sub", "exp"}, SECRET_KEY, "HS256")`, `get_current_user` raising 401 on `InvalidTokenError`, secret from `openssl rand -hex 32`. |
| `Docs` | FastAPI `tutorial/handling-errors`: `@app.exception_handler(MyException)` returning any `Response`. `reference/responses`: `set_cookie(key, value, max_age, path, secure, httponly, samesite)` / `delete_cookie(key, path, ...)` — delete must pass the same `path` as set. |
| `Docs` | PyJWT CHANGELOG: minimum HMAC key length (CWE-326) warns by default, `options={"enforce_minimum_key_length": True}` raises `InvalidKeyError`; exception hierarchy — everything relevant subclasses `InvalidTokenError`. |
| `Inference` | `fetch('/dashboard/_search.json')` in `base.html:1204` sends `Accept: */*` (browser default for `fetch`); not executed in a browser during research. |

---

## Local Findings

- **Relevant files, modules, scripts, docs, tests:** `app/core/dashboard_auth.py`,
  `app/core/auth.py` (pattern), `app/core/errors.py`, `app/core/config.py:200-206`,
  `app/core/lifespan.py`, `app/routers/{dashboard,dashboard_prompts,main}.py`,
  `app/templates/base.html:1050-1067` (topbar), `app/templates/agent_config.html` (extends
  pattern), `.env.example:110-116`, `tests/conftest.py:55-97`,
  `tests/api/agent_config/test_dashboard_auth.py` (+ the two per-`Settings` modules).
- **Existing abstractions or extension points:** `AppError`/`AuthError` + single envelope
  handler; router-level `dependencies=[...]`; `get_settings` monkeypatch seam; frozen
  principal dataclass (`AuthUser`).
- **Conventions worth preserving:** services/deps raise domain errors, never `HTTPException`;
  `include_in_schema=False` on dashboard routers; templates resolved relative to the router
  file; constant-time compare with `TypeError` guard.
- **What can likely be reused:** `AuthError` (subclass it), `_handle_app_error` (call it),
  `Settings` + `.env.example` block, `_build_client` helper in the existing auth test, the
  `AuthUser` shape.
- **What appears missing locally:** any login template, any cookie helper, any HS256 signing;
  `warnings` filter config in pytest (none — warnings are noise, not failures).

---

## Upstream Findings

- **Repositories inspected:** fastapi-users (docs: cookie transport, JWT strategy, logout
  flow, 8.x→9.x migration).
- **Pattern or capability already present upstream:** transport/strategy split; cookie defaults
  `secure=True, httponly=True, samesite="lax"`; logout is a POST that clears the cookie;
  JWT lifetime = cookie max-age.
- **Files, modules, or areas worth modeling:** `CookieTransport.get_login_response` /
  `get_logout_response` (set/delete with identical path+flags).
- **How closely the upstream pattern matches this repo:** closely for the transport half; the
  user-manager/DB half is irrelevant (one env identity).
- **Any upstream gaps or uncertainties:** fastapi-users' `secure` defaults to `True` in every
  env; the design's `Secure iff is_production` is a deliberate local-dev relaxation.

---

## Docs Findings

- **Official sources checked:** fastapi.tiangolo.com (`tutorial/security/oauth2-jwt`,
  `tutorial/handling-errors`, `reference/security`, `reference/responses`), PyJWT CHANGELOG +
  `docs/usage.md`, fastapi-users docs.
- **Version-matched vs latest-stable status:** FastAPI docs are for current stable (≥0.136,
  matches); PyJWT CHANGELOG entries for the key-length warning and `require` option match the
  installed 2.13.0 (verified empirically, not only from docs).
- **Built-in capabilities that already support the feature:** `APIKeyCookie`,
  `OAuth2PasswordRequestForm`, `Response.set_cookie/delete_cookie`, `@app.exception_handler`,
  `jwt.encode/decode` with `algorithms`, `leeway`, `options.require`.
- **Current recommended APIs or workflows:** exactly the tutorial's; `Annotated[..., Depends()]`
  style already used in this repo.
- **Important caveats, deprecations, or migration notes:**
  1. `jwt.decode` does **not** require `exp` unless `options={"require": ["exp", ...]}` —
     add it, or a hand-crafted never-expiring token signed with a leaked key stays valid.
  2. `InsecureKeyLengthWarning` at `encode` for HMAC keys < 32 bytes — D4's floor handles it;
     tests can additionally pass `options={"enforce_minimum_key_length": True}`.
  3. `delete_cookie` must repeat `path="/dashboard"` (and flags) or the browser keeps the cookie.
  4. Starlette's `TestClient` warns `StarletteDeprecationWarning` about httpx — pre-existing,
     unrelated.

---

## Recommendation

- **Primary recommendation:** use built-in (FastAPI security classes + PyJWT), modelled on
  fastapi-users' transport/strategy split, implemented as specified in `design.md` with two
  additions: `options={"require": ["exp", "iat", "sub"]}` on decode, and `delete_cookie` with
  the same `path`/flags as `set_cookie`.
- **Why this is the lightest credible path:** zero new dependencies (ledger rows 2, 3); the
  guard mechanism (router-level `Depends`) and the test seams (`dependency_overrides`,
  `get_settings` monkeypatch) already exist; the only genuinely new surface is one router with
  three routes and one template.
- **Why the next-best alternative lost:** *adapt upstream* (add `fastapi-users`) brings a user
  manager, DB models and password hashing for a single env identity — unjustified scope;
  *Starlette `SessionMiddleware`* needs `itsdangerous` (not installed) and stores state
  app-wide for a `/dashboard`-only concern; *keep HTTP Basic* was rejected by the user (E001).
- **What would change this recommendation:** a second operator identity or password rotation
  that must invalidate sessions → add a `pwd` fingerprint claim or move to fastapi-users.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:** (1) handler placed outside `register_exception_handlers` → 500 on JSON
  path (verified failure mode); (2) missing `require` → non-expiring tokens; (3) `Path`
  mismatch between set and delete → logout appears to fail; (4) ruff-on-edit hook deletes
  imports added before their first use — write import + usage in one edit.
- **Evidence gaps:** `Accept` header of the palette `fetch` is inferred from browser defaults,
  not captured; the HTML form's `required` attribute behaviour is browser-side and untested here.
- **Version uncertainties:** none — every claim was run against the installed venv.
- **Follow-up questions for the user:** none required. (Optional: should `Secure` also be set
  when a reverse proxy terminates TLS in non-production? Default stays `is_production` only.)

---

## Source Pack

- **Local files read:** `apps/api/app/core/dashboard_auth.py`, `app/core/auth.py`,
  `app/core/errors.py`, `app/core/config.py`, `app/core/lifespan.py`, `app/core/middleware.py`,
  `app/exceptions.py`, `app/routers/dashboard.py`, `app/routers/dashboard_prompts.py`,
  `app/routers/main.py`, `app/templates/base.html`, `app/templates/agent_config.html`,
  `requirements.txt`, `.env.example`, `docker-compose.yml`, `tests/conftest.py`,
  `tests/api/agent_config/test_dashboard_auth.py`, `test_agent_runs_dashboard.py`,
  `test_agent_run_detail_page.py`, `.github/workflows/*.yml`, `specs/review-a-security-hardening/design.md`,
  `docs/solutions/INDEX.md` (no auth/cookie entry), `specs/dashboard-auth-required/{SUMMARY,ESCALATIONS,design}.md`.
- **Upstream repositories or pages checked:**
  https://github.com/fastapi-users/fastapi-users (docs/configuration/authentication/transports/cookie.md,
  docs/usage/flow.md, docs/migration/8x_to_9x.md)
- **Official docs domains or pages checked:**
  https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt ,
  https://fastapi.tiangolo.com/tutorial/handling-errors ,
  https://fastapi.tiangolo.com/reference/security ,
  https://fastapi.tiangolo.com/reference/responses ,
  https://github.com/jpadilla/pyjwt/blob/master/CHANGELOG.rst ,
  https://github.com/jpadilla/pyjwt/blob/master/docs/usage.md

---

## Evidence Boundary

> Confirmed from artifacts: installed versions; router-level guard wiring; the nine `/dashboard`
> test files and which fixture each uses; Starlette handler selection and re-raise → 500;
> PyJWT key-length warning, future-`iat` rejection, and decode-without-`exp` acceptance;
> `APIKeyCookie` signature; CI/compose/.env have no `DASHBOARD_*` vars.
> Inferred from patterns: `fetch` sends `Accept: */*`; browsers honour `required` on the form.
> Not checked: rendering of `login.html` in a real browser; behaviour behind a TLS-terminating
> proxy (`Secure` flag); Docker Python 3.12 vs local 3.14 differences (none expected — no
> version-specific syntax planned).
