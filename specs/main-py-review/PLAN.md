---
slug: main-py-review
status: shipped
owner: Minh Tran
created: 2026-06-22
---

# `app/main.py` Best-Practices Hardening — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Fix the one verified correctness bug (unhandled 500s escape the JSON error envelope) and slim `create_app` by extracting handlers/middleware into focused `core/` modules, adding the in-scope missing middleware (GZip, request-ID) and a production CORS guard.

**Architecture:** Keep the app-factory pattern. Move the four exception handlers into `app/core/errors.py` (`register_exception_handlers(app, settings)`) and all middleware into `app/core/middleware.py` (`register_middleware(app, settings)`), leaving `create_app` a thin orchestrator. The 500 fix is two-part because Starlette binds the catch-all `Exception` handler to the *outermost* `ServerErrorMiddleware` (verified, `starlette/applications.py:63-71`): a handler restores the JSON body, and a `try/except` in the logging middleware restores the access-log line.

**Tech Stack:** FastAPI / Starlette 1.2.1, Pydantic v2 + pydantic-settings, pytest + `fastapi.testclient.TestClient`, ruff.

**Source artifacts:** `specs/main-py-review/REVIEW.md` (verified findings), `specs/main-py-review/SUMMARY.md` (intake — high-risk lane).

**Lane:** high-risk. After each wave, run the full suite (`make test`) before advancing.

---

## 1. Motivation

`app/main.py` advertises "every error leaves the API in the same JSON envelope," but a verified `TestClient` probe shows unhandled (non-`AppError`) exceptions return `text/plain "Internal Server Error"` with no envelope, no access-log line, and no rate-limit headers — the worst case escapes the contract. Separately, `create_app` carries ~150 lines of inline handlers/middleware ("a lot of config") and lacks standard middleware (GZip, request-ID).

## 2. Non-goals

- No auth, pagination, or enforced rate limiting (out of scope per `CLAUDE.md`). The `X-RateLimit-*` headers remain **informational/unenforced**.
- No new endpoints (avoids the public-contract new-endpoint hard gate).
- No change to the success-path response shape of any existing route.

## 3. Success Criteria

- An unhandled exception returns the JSON envelope (`{error, message, status_code, path}`), `content-type: application/json`, status 500, **and** is access-logged.
- In `production`, the 500 `message` does not leak the exception string/traceback.
- `create_app` is a thin orchestrator; handlers live in `core/errors.py`, middleware in `core/middleware.py`.
- GZip compresses large responses; every response carries an `X-Request-ID` echoed/generated, present in the access-log line and in error envelopes.
- `Settings` rejects `allow_credentials=True` with wildcard origins when `is_production`.
- Full suite green on SQLite (`make test`) and unchanged behavior for all existing error/route tests.

## 4. Tasks

> Each task has a fenced `xml` block (parsed by the render-plan hook) followed by bite-sized TDD steps. Run `ruff check app tests && ruff format app tests` after each task — note the `ruff-on-edit` hook strips imports added before their first use, so add import + usage together.

### Wave 1 — Behavior-preserving extraction (slim `create_app`, split P4)

This wave changes **no behavior** — it's a pure refactor done under a green suite, so any later test failure is attributable to the feature waves, not the move.

#### Task 1.1 — Extract handlers + middleware into `core/`, split logging from rate-limit headers

```xml
<task id="1.1" wave="1">
  <files>app/main.py, app/core/errors.py, app/core/middleware.py</files>
  <action>Create app/core/errors.py with register_exception_handlers(app, settings) holding _error_body, _HTTP_ERROR_LABELS, and the existing AppError / StarletteHTTPException / RequestValidationError handlers (verbatim logic). Create app/core/middleware.py with register_middleware(app, settings) holding the request-logging middleware (timing + access line ONLY) and a SEPARATE rate-limit-header middleware (P4 split), plus the existing CORSMiddleware registration. Reduce create_app to: get_settings, configure_logging, build FastAPI(...), register_exception_handlers(app, settings), register_middleware(app, settings), include_router, return. Keep _operation_id in main.py. No behavior change.</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi && python -m pytest tests/infra -q</verify>
  <done>tests/infra passes unchanged; create_app body is <30 lines; errors.py and middleware.py own their concerns.</done>
</task>
```

- [ ] **Step 1: Run the infra suite first to capture the green baseline**
  Run: `python -m pytest tests/infra -q` — Expected: all pass (this is the regression guard for the refactor).
- [ ] **Step 2: Create `app/core/errors.py`**
  Move `_error_body`, `_HTTP_ERROR_LABELS`, and the three existing handlers out of `create_app`. Make them module-level functions registered inside `register_exception_handlers`:

```python
"""Exception handlers — the single JSON error envelope (kept FastAPI-side)."""
import logging
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings
from app.exceptions import AppError

logger = logging.getLogger(__name__)

_HTTP_ERROR_LABELS = {
    400: "BadRequest", 401: "Unauthorized", 403: "Forbidden", 404: "NotFound",
    405: "MethodNotAllowed", 409: "Conflict", 422: "UnprocessableEntity",
    429: "TooManyRequests",
}

def _error_body(error, message, status_code, request, **extra):
    return {"error": error, "message": message, "status_code": status_code,
            "path": request.url.path, **extra}

def register_exception_handlers(app: FastAPI, settings: Settings) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning("%s on %s %s: %s", type(exc).__name__, request.method,
                       request.url.path, exc.detail)
        extra = {"hint": exc.hint} if exc.hint else {}
        return JSONResponse(status_code=exc.status_code,
            content=_error_body(type(exc).__name__, exc.detail, exc.status_code, request, **extra))

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        label = _HTTP_ERROR_LABELS.get(exc.status_code, "HTTPException")
        return JSONResponse(status_code=exc.status_code,
            content=_error_body(label, str(exc.detail), exc.status_code, request))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("ValidationError", "Request validation failed",
                status.HTTP_422_UNPROCESSABLE_ENTITY, request,
                hint=("Inspect the 'errors' array for per-field problems (each entry has "
                      "'loc', 'msg', and 'type'). Fix the listed fields and retry."),
                errors=jsonable_encoder(exc.errors())))
```

- [ ] **Step 3: Create `app/core/middleware.py`** with logging and rate-limit-header as two middlewares + CORS:

```python
"""HTTP middleware registration."""
import logging
import time
from collections.abc import Awaitable, Callable
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings

logger = logging.getLogger(__name__)

def register_middleware(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def _log_requests(request: Request,
                            call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("%s %s → %d (%.1fms)", request.method, request.url.path,
                    response.status_code, elapsed_ms)
        return response

    @app.middleware("http")
    async def _rate_limit_headers(request: Request,
                                  call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        limit = settings.rate_limit_nominal
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
        return response

    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_methods, allow_headers=settings.cors_headers)
```

> Note on order: `@app.middleware` prepends (last-declared runs outermost), and `add_middleware(CORS)` runs after both. Net inbound order stays CORS → rate-limit → logging → route, matching today. Wave 3 inserts GZip + request-ID here.

- [ ] **Step 4: Slim `app/main.py`** to the orchestrator; delete the moved code; keep `_operation_id` and the `docs_kwargs` prod-gating:

```python
def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    docs_kwargs = ({"docs_url": None, "redoc_url": None, "openapi_url": None}
                   if settings.is_production else {})
    app = FastAPI(title=settings.app_name, description=settings.app_description,
                  version=settings.app_version, lifespan=lifespan,
                  generate_unique_id_function=_operation_id, **docs_kwargs)
    register_exception_handlers(app, settings)
    register_middleware(app, settings)
    app.include_router(api_router)
    return app
```

- [ ] **Step 5: Lint + run the infra suite, then the full suite**
  Run: `ruff check app tests && python -m pytest tests/infra -q` — Expected: PASS, no diffs in behavior.
  Run: `make test` — Expected: full suite green (baseline preserved).

---

### Wave 2 — P1: the verified 500 bug

#### Task 2.1 — Catch-all `Exception` handler + access-log on failure (TDD)

```xml
<task id="2.1" wave="2">
  <files>app/core/errors.py, app/core/middleware.py, tests/infra/test_errors.py</files>
  <action>Add @app.exception_handler(Exception) in errors.py returning the JSON envelope (error="InternalServerError", status 500), logging via logger.exception; in production (settings.is_production) the message is the literal "Internal server error", else f"{type(exc).__name__}: {exc}". Wrap call_next in _log_requests with try/except that logs the failed request (status 500) with timing via logger.exception and re-raises. Add regression tests proving a raised exception yields a JSON 500 envelope (not plaintext) and that prod hides the detail.</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi && python -m pytest tests/infra/test_errors.py -q</verify>
  <done>500 path returns application/json envelope; prod message is generic; access line emitted on failure; all prior error tests still pass.</done>
</task>
```

- [ ] **Step 1: Write the failing test** in `tests/infra/test_errors.py` (a local app + non-raising client, since the shared `client` fixture uses `raise_server_exceptions=True`):

```python
from fastapi.testclient import TestClient
from app.main import create_app

def test_unhandled_exception_uses_envelope():
    app = create_app()

    @app.get("/__boom")
    def _boom():
        raise ValueError("kaboom")

    # No `with` → lifespan/DB startup is skipped; the route raises before any DB use.
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.get("/__boom")
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    _assert_envelope(body, 500, "/__boom")
    assert body["error"] == "InternalServerError"
```

- [ ] **Step 2: Run it to verify it fails**
  Run: `python -m pytest tests/infra/test_errors.py::test_unhandled_exception_uses_envelope -v`
  Expected: FAIL — body is plaintext `Internal Server Error`, `resp.json()` raises / content-type is `text/plain`.
- [ ] **Step 3: Add the handler** to `register_exception_handlers` in `app/core/errors.py`:

```python
    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        message = ("Internal server error" if settings.is_production
                   else f"{type(exc).__name__}: {exc}")
        return JSONResponse(status_code=500,
            content=_error_body("InternalServerError", message, 500, request))
```

- [ ] **Step 4: Restore access logging on failure** in `_log_requests` (`app/core/middleware.py`):

```python
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception("%s %s → 500 (%.1fms)", request.method, request.url.path, elapsed_ms)
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("%s %s → %d (%.1fms)", request.method, request.url.path,
                    response.status_code, elapsed_ms)
        return response
```

- [ ] **Step 5: Run the envelope test — expect PASS**
  Run: `python -m pytest tests/infra/test_errors.py::test_unhandled_exception_uses_envelope -v` — Expected: PASS.
- [ ] **Step 6: Add the production-hides-detail test** (use monkeypatch + clear the `get_settings` cache):

```python
def test_unhandled_exception_hides_detail_in_production(monkeypatch):
    from app.core import config
    monkeypatch.setenv("ENVIRONMENT", "production")
    config.get_settings.cache_clear()
    try:
        app = create_app()

        @app.get("/__boom")
        def _boom():
            raise ValueError("secret-trace")

        c = TestClient(app, raise_server_exceptions=False)
        body = c.get("/__boom").json()
        assert body["message"] == "Internal server error"
        assert "secret-trace" not in body["message"]
    finally:
        config.get_settings.cache_clear()
```

> Note: `create_app()` in production sets `openapi_url=None`; this test doesn't hit `/openapi.json`, so that's fine. The `cache_clear()` in `finally` prevents leaking the prod settings into other tests.

- [ ] **Step 7: Add a failure-is-logged test** with `caplog`:

```python
def test_unhandled_exception_is_access_logged(caplog):
    import logging
    app = create_app()

    @app.get("/__boom")
    def _boom():
        raise ValueError("kaboom")

    c = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="app.core.middleware"):
        c.get("/__boom")
    assert any("→ 500" in r.message for r in caplog.records)
```

- [ ] **Step 8: Lint + run the full infra suite, then full suite**
  Run: `ruff check app tests && python -m pytest tests/infra/test_errors.py -q` — Expected: PASS.
  Run: `make test` — Expected: green.

---

### Wave 3 — Additive middleware + guards (parallel; disjoint files)

Files are disjoint across 3.1 / 3.2 / 3.3 so they may run in parallel.

#### Task 3.1 — GZip + request-ID middleware

```xml
<task id="3.1" wave="3">
  <files>app/core/middleware.py, app/core/errors.py, tests/infra/test_middleware.py</files>
  <action>In register_middleware: add GZipMiddleware (minimum_size=1000) and a request-ID middleware that reads X-Request-ID or generates uuid4().hex, stores it on request.state.request_id, and sets it on the response header; include request.state.request_id in the access-log line. In errors.py _error_body, append request_id (read via getattr(request.state, "request_id", None)) when present, so error envelopes carry it. Add tests for gzip and request-ID echo/generate.</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi && python -m pytest tests/infra/test_middleware.py -q</verify>
  <done>Large responses are gzipped when Accept-Encoding: gzip; every response has X-Request-ID; a supplied X-Request-ID is echoed; error envelopes include request_id.</done>
</task>
```

- [ ] **Step 1: Write failing tests** in new `tests/infra/test_middleware.py`:

```python
from fastapi.testclient import TestClient

def test_request_id_generated(client: TestClient):
    resp = client.get("/")
    rid = resp.headers.get("X-Request-ID")
    assert rid and len(rid) >= 8

def test_request_id_echoed(client: TestClient):
    resp = client.get("/", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["X-Request-ID"] == "abc-123"

def test_gzip_compresses_large_response(client: TestClient):
    # /flights/search returns a large JSON list; ask for gzip explicitly.
    resp = client.get("/flights/search",
        params={"origin": "DAD", "destination": "SGN", "departure_date": "2026-12-01"},
        headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"
```

- [ ] **Step 2: Run to verify failure** — Run: `python -m pytest tests/infra/test_middleware.py -q` — Expected: FAIL (no header / no encoding).
- [ ] **Step 3: Implement** in `app/core/middleware.py`:

```python
import uuid
from fastapi.middleware.gzip import GZipMiddleware
# ...
    @app.middleware("http")
    async def _request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    app.add_middleware(GZipMiddleware, minimum_size=1000)
```
  Add `request.state.request_id` to the `_log_requests` access line (e.g. trailing ` [rid=%s]`). Ensure `_request_id` is declared so it runs *before* `_log_requests` reads it (declare `_request_id` after `_log_requests` since `@app.middleware` prepends — later declaration = outer = runs earlier inbound).

- [ ] **Step 4: Thread request_id into the envelope** in `app/core/errors.py` `_error_body`:

```python
def _error_body(error, message, status_code, request, **extra):
    rid = getattr(request.state, "request_id", None)
    body = {"error": error, "message": message, "status_code": status_code,
            "path": request.url.path}
    if rid:
        body["request_id"] = rid
    return {**body, **extra}
```

- [ ] **Step 5: Run tests — expect PASS**; then `make test`.

#### Task 3.2 — Production CORS guard in `Settings`

```xml
<task id="3.2" wave="3">
  <files>app/core/config.py, tests/infra/test_cors.py, tests/infra/test_meta.py, tests/infra/test_errors.py</files>
  <action>Add a Pydantic model_validator(mode="after") to Settings that raises ValueError when is_production and cors_allow_credentials is True and "*" is in cors_origins (browsers + Starlette reflect-any-origin-with-credentials is unsafe in prod). Dev/test unaffected. Add tests covering: prod+wildcard+credentials raises; prod+explicit-origins+credentials ok; dev+wildcard ok. SCOPE WIDENED (gap found in execution): two pre-existing prod-Settings tests now construct an invalid prod config and must pass an explicit non-wildcard origin — test_meta.py::test_docs_hidden_in_production (add cors_origins=["https://app.example.com"]) and test_errors.py::test_unhandled_exception_hides_detail_in_production (set CORS_ORIGINS env to a JSON list).</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi && python -m pytest tests/infra/test_cors.py -q</verify>
  <done>Settings construction fails fast on the unsafe prod CORS combo; permissive dev default still works.</done>
</task>
```

- [ ] **Step 1: Write failing tests** in new `tests/infra/test_cors.py`:

```python
import pytest
from pydantic import ValidationError
from app.core.config import Settings

def test_prod_wildcard_with_credentials_rejected():
    with pytest.raises(ValidationError):
        Settings(environment="production", cors_origins=["*"], cors_allow_credentials=True)

def test_prod_explicit_origins_ok():
    s = Settings(environment="production",
                 cors_origins=["https://app.example.com"], cors_allow_credentials=True)
    assert s.is_production

def test_dev_wildcard_ok():
    s = Settings(environment="development", cors_origins=["*"], cors_allow_credentials=True)
    assert not s.is_production
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (no validator → no raise).
- [ ] **Step 3: Implement** in `app/core/config.py`:

```python
from pydantic import model_validator
# ...
    @model_validator(mode="after")
    def _guard_prod_cors(self) -> "Settings":
        if self.is_production and self.cors_allow_credentials and "*" in self.cors_origins:
            raise ValueError(
                "Refusing to run in production with cors_allow_credentials=True and a "
                "wildcard origin ('*'): set explicit CORS_ORIGINS.")
        return self
```

- [ ] **Step 4: Run tests — expect PASS**; then `make test`.

#### Task 3.3 (optional, low priority) — Runtime operationId-uniqueness guard

> `tests/infra/test_operation_ids.py:19` already asserts uniqueness at test time. This adds a *runtime* fail-fast for non-test environments. Include only because full scope was chosen; skip if trimming.

```xml
<task id="3.3" wave="3">
  <files>app/main.py, tests/infra/test_operation_ids.py</files>
  <action>After include_router in create_app, assert OpenAPI operationIds are unique across APIRoutes (raise RuntimeError naming the collision) so a duplicate handler name fails app startup, not just CI. Extend test_operation_ids.py with a test that a deliberately duplicated handler name raises at create_app/openapi time.</action>
  <verify>cd /Users/minhtran/Documents/minhtran3124/developer/travel-pi && python -m pytest tests/infra/test_operation_ids.py -q</verify>
  <done>Duplicate operationIds raise at startup; existing uniqueness test still passes.</done>
</task>
```

- [ ] **Step 1: Implement** the guard in `create_app` after `include_router`:

```python
    from fastapi.routing import APIRoute
    ids = [r.operation_id or r.name for r in app.routes if isinstance(r, APIRoute)]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise RuntimeError(f"Duplicate operationIds (breaks TS codegen): {sorted(dupes)}")
```

- [ ] **Step 2: Add a test** asserting a duplicated handler name trips the guard; run `python -m pytest tests/infra/test_operation_ids.py -q`.

---

## 5. Risks

- **Public-contract change:** the 500 response shape changes (plaintext → JSON envelope). Intended and strictly more consistent, but `risk-corroboration.sh` may flag it — authorize with `RISK_WARN_CATEGORIES="public-contract"` (memory `public-contract-hard-gate`).
- **Middleware ordering:** request-ID must run before `_log_requests` reads `request.state.request_id`; GZip must not double-compress. Verified by the Wave-3 tests.
- **Settings cache leakage in tests:** the prod-CORS / prod-message tests mutate env + clear `get_settings` cache — always `cache_clear()` in `finally` to avoid cross-test bleed (see Task 2.1 Step 6).
- **Stale `travel.db`:** no schema change here, so the `stale-travel-db` risk does not apply.
- **caplog after `create_app()`:** `create_app()` runs `configure_logging()` → `dictConfig`, whose `root.handlers=["console"]` **replaces** the root handler list, detaching pytest's caplog handler. Any in-test `create_app()` followed by a caplog assertion must re-attach `caplog.handler` after the call (seen in Task 2.1 Step 7 on Python 3.14).

## 6. Status Log

- 2026-06-22 — Plan drafted from REVIEW.md, reviewer-approved. Status → active.
- 2026-06-22 — Isolated on in-place branch `feat/main-py-review` off `v3` (separate-dir worktree rejected: entire `.claude/` harness + `specs/` are untracked and would be orphaned; remote is `github` not `origin` and `v3` is 184 commits ahead of `main`, so the native tool's `fresh`/origin-main base was wrong). Baseline: 682 passed.
- 2026-06-22 — All waves executed via subagent-driven-development; status → shipped. Final: **692 passed**, ruff clean. Commits:
  - Wave 1 / Task 1.1 — `b866eec` refactor(main): extract handlers + middleware, split P4
  - Wave 2 / Task 2.1 — `d5170a1` fix(errors): JSON envelope for unhandled 500s + log failures (P1)
  - Wave 3 / Task 3.1 — `9212c81` feat(middleware): gzip + request-ID (P3)
  - Wave 3 / Task 3.2 — `9b78f8e` feat(config): reject wildcard CORS + credentials in prod (P6; scope widened to 2 prod-test files)
  - Wave 3 / Task 3.3 — `bb16b61` feat(main): fail startup on duplicate operationIds (P5; guard filtered to include_in_schema)
- 2026-06-22 — shipped via `feat/main-py-review` (PR #16 → base `v3`): https://github.com/minhtran3124/travel-pi/pull/16
- 2026-06-22 — Harness-Deltas for `/compound`: (1) PLAN caplog recipe must re-attach handler after in-test `create_app()`; (2) Task 3.2 `<files>`/"691" target was self-inconsistent (validator breaks unlisted prod tests); (3) Task 3.3 guard code must mirror the test-time `include_in_schema` filter; (4) the commit hook aborts `git add && git commit` chains — stage and commit as separate commands.
