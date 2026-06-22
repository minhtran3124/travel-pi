"""HTTP middleware registration."""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings

logger = logging.getLogger(__name__)


def register_middleware(app: FastAPI, settings: Settings) -> None:
    """Register the request-logging, rate-limit-header, and CORS middleware.

    ``@app.middleware`` prepends (last-declared runs outermost), and
    ``add_middleware(CORS)`` runs after both — so declaring ``_log_requests``
    before ``_rate_limit_headers`` keeps the net inbound order
    CORS → rate-limit → logging → route, matching the original ``create_app``.
    """

    # Log one line per request: method, path, status, and how long it took.
    # This is the single source of access logs (Uvicorn's is silenced in
    # app.core.logging), so it works the same however the app is launched.
    @app.middleware("http")
    async def _log_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # The catch-all Exception handler is bound to the outermost
            # ServerErrorMiddleware (above this one), so the failed request
            # never reaches the access line below — log it here and re-raise.
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "%s %s → 500 (%.1fms)",
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    # Informational, unenforced rate-limit headers on every response.
    @app.middleware("http")
    async def _rate_limit_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        limit = settings.rate_limit_nominal
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(limit)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
        return response

    # CORS — wide open for local dev so the FE/agent can call from anywhere.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_methods,
        allow_headers=settings.cors_headers,
    )
