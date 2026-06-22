# `app/main.py` — Best-Practices Review

**Date:** 2026-06-22 · **Scope:** `app/main.py` (app factory) and its immediate
collaborators (`core/config.py`, `core/lifespan.py`, `core/logging.py`).
**Method:** code read + verified against installed `starlette 1.2.1` source and a
live `TestClient` probe (not from memory). Context7 is not configured in this repo
(`.mcp.json` has only `code-review-graph`), so behavior was confirmed empirically.

---

## TL;DR

`main.py` is a solid, modern FastAPI factory (lifespan, settings, prod-docs gating,
stable operationIds, uniform error envelope). Two things to fix and one to tidy:

1. **P1 — The error-envelope contract is broken for unhandled 500s.** Verified: a
   bug that raises a non-`AppError` returns `text/plain "Internal Server Error"`,
   with **no** envelope, **no** access-log line, and **no** rate-limit headers.
2. **P2 — `create_app` does too much** ("a lot of config"). 150 lines, four inline
   closures. Extract handlers + middleware into `core/` modules.
3. **P3 — Genuinely missing middleware:** GZip and a request-ID/correlation-ID. CORS
   is permissive-with-credentials (fine for dev, a prod smell).

---

## What's already good (keep)

- App-factory (`create_app`) + module-level `app` for `uvicorn app.main:app`. ✅
- `lifespan` context manager (not deprecated `on_event`). ✅
- `pydantic-settings` + `@lru_cache get_settings()`; `Literal` types fail bad env
  values fast. ✅
- Docs/redoc/openapi disabled in production. ✅
- Stable `operationId = route.name` for clean TS codegen. ✅
- One uniform JSON error envelope for `AppError`, `HTTPException`, and
  `RequestValidationError`; services stay HTTP-free. ✅ (but see P1)
- Health probes (`/healthz`, `/readyz`) and root (`/`) already exist in routers —
  `main.py` correctly does *not* duplicate them. ✅

---

## Findings (prioritized)

### P1 — No catch-all `Exception` (500) handler — envelope contract is broken  [VERIFIED]

The module documents "every error — domain, HTTP, or request-validation — leaves the
API in the same JSON envelope." That holds for those three classes, but **not** for an
unhandled exception (a real bug). Live probe:

```
GET /__boom  (handler raises ValueError)
  status: 500
  content-type: text/plain; charset=utf-8
  body: 'Internal Server Error'
  X-RateLimit-Limit present: False
  access-log line emitted: NO
```

Compare the 404, which is correct:

```
GET /missing
  body: {"error":"NotFound","message":"Not Found","status_code":404,"path":"/missing"}
  X-RateLimit-Limit present: True
  access-log line emitted: YES
```

So the single most operationally important failure (a 500) is the one that escapes the
envelope, is invisible to the access log, and ships no headers — exactly backwards for
an API consumed by agents that parse failures uniformly.

**Subtlety that shapes the fix** (verified in `starlette/applications.py:63-71`): the
catch-all `Exception`/`500` handler is bound to `ServerErrorMiddleware`, the
**outermost** layer — *outside* the user middleware (`_log_requests`, CORS). Stack is:

```
ServerErrorMiddleware (500/Exception handler lives here)   ← outermost
  └─ CORSMiddleware
     └─ _log_requests (BaseHTTPMiddleware)
        └─ ExceptionMiddleware (AppError / HTTPException / validation handlers)
           └─ router
```

Therefore adding an `Exception` handler alone fixes the **body** but the 500 response
still bypasses `_log_requests` and CORS → still no access line, no rate-limit header,
**no CORS headers on 500s either**. The complete fix is two parts:

1. Register a catch-all handler that returns the envelope and logs with
   `logger.exception(...)`. In production, return a generic message — never leak the
   exception string / traceback into `message`.
2. Wrap `call_next` in `_log_requests` with `try/except` to emit the access line for a
   failed request (status 500, with timing) and re-raise so `ServerErrorMiddleware`
   still produces the response.

```python
# core/errors.py
@app.exception_handler(Exception)
async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    message = "Internal server error" if settings.is_production else f"{type(exc).__name__}: {exc}"
    return JSONResponse(
        status_code=500,
        content=_error_body("InternalServerError", message, 500, request),
    )
```

```python
# in _log_requests
start = time.perf_counter()
try:
    response = await call_next(request)
except Exception:
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.exception("%s %s → 500 (%.1fms)", request.method, request.url.path, elapsed_ms)
    raise
```

> Note: `TestClient` defaults to `raise_server_exceptions=True`, which re-raises before
> you see the 500. Add a regression test with `TestClient(app, raise_server_exceptions=False)`
> asserting the JSON envelope + `content-type: application/json` on a route that raises.

---

### P2 — `create_app` carries too much config (the "a lot of config" complaint)

~150 lines, four inline closures (`_error_body`, three exception handlers, one
middleware) plus the label map, all nested in the factory. This is the readability
problem the prompt names. The handlers/middleware are pure functions of `(app, settings)`
and don't need closure scope — extract them:

```
app/core/
  errors.py       # register_exception_handlers(app, settings): AppError, HTTPException,
                  #   RequestValidationError, Exception; owns _error_body + label map
  middleware.py   # register_middleware(app, settings): request-log, (gzip), CORS
```

`create_app` then reads as intent, not plumbing:

```python
def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(..., lifespan=lifespan, generate_unique_id_function=_operation_id, **docs_kwargs)
    register_exception_handlers(app, settings)
    register_middleware(app, settings)
    app.include_router(api_router)
    return app
```

Benefit beyond looks: each registrar is unit-testable in isolation, and it matches the
repo's existing "one concern per file" layering.

---

### P3 — Missing middleware (what the prompt hinted at)

Scaled to CLAUDE.md's "keep it minimal" rule (no auth/pagination/rate-limiting). The
**in-scope, high-value** additions:

- **`GZipMiddleware`** — one line; compresses the larger JSON list responses
  (flights/hotels/places). Cheap, standard.
  `app.add_middleware(GZipMiddleware, minimum_size=1000)`
- **Request-ID / correlation-ID** — generate or honor `X-Request-ID`, echo it on the
  response, include it in the access-log line *and* the error envelope. This is the
  highest-leverage observability add for an agent-consumed API: a failed call can be
  traced to one log line. (Pure-ASGI middleware, or `contextvars` + the existing
  `BaseHTTPMiddleware`.)

**Production-hardening, optional for a mock — mention, don't necessarily build:**

- **`TrustedHostMiddleware`** — restrict `Host` in production.
- **Security headers** (`X-Content-Type-Options: nosniff`, etc.).
- **Proxy headers** — already covered by `uvicorn[standard] --proxy-headers` if you run
  behind the Docker/ingress proxy; no app code needed.

---

### P4 — `_log_requests` mixes two unrelated concerns

It does access logging **and** injects the (fake, informational) `X-RateLimit-*`
headers. They're unrelated, and the headers are silently absent on 500s (P1). Either
split into two middlewares or move the rate-limit headers into a tiny dedicated one and
keep `_log_requests` purely about logging + timing. Minor, but it's part of why the file
feels like "a lot of config."

---

### P5 — `operationId = route.name` can collide

`_operation_id` returns the bare handler function name for stable codegen. If two
routers ever define handlers with the same function name (e.g. two `list_all`), OpenAPI
operationIds collide → broken/duplicated TS types, the exact thing this is meant to
protect. Cheap safety net: assert uniqueness once at startup (in `create_app` after
`include_router`, iterate `app.routes` and raise on a duplicate `operation_id`). Low
probability, high blast radius on the FE.

---

### P6 — CORS: `allow_origins=["*"]` + `allow_credentials=True`  [VERIFIED behavior]

Not protocol-broken: `starlette 1.2.1` (cors.py:167-168) reflects the request's `Origin`
instead of sending `*` when credentials are allowed, so browsers accept it. But the
effect is "**any** origin may send credentials" — fine for local dev, a real risk if
this config ever reaches a deployment. Since `Settings` already centralizes CORS, the
clean guard is: reject `["*"]` (or refuse `allow_credentials` with `*`) when
`is_production`, e.g. a `model_validator` on `Settings`. No `main.py` change needed.

---

## Suggested wave plan (if you choose to implement)

| Wave | Task | Files |
|------|------|-------|
| 1 | P1: catch-all 500 handler + middleware try/except + regression test | `core/main.py` (or new `core/errors.py`), `tests/` |
| 1 | P3: GZip middleware | `main.py` / `core/middleware.py` |
| 2 | P2: extract `core/errors.py` + `core/middleware.py`, slim `create_app` | `main.py`, `core/errors.py`, `core/middleware.py` |
| 2 | P5: operationId uniqueness assertion | `main.py` |
| 3 (opt) | P3: request-ID middleware + envelope/log integration | `core/middleware.py`, `core/errors.py` |
| 3 (opt) | P6: prod CORS guard in `Settings` | `core/config.py` |

P1 is the only one that's a correctness bug; the rest are structure/observability.
P2 + P3(gzip) directly answer "lots of config, missing middleware."
