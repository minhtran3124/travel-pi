"""HTTP middleware registration."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import Settings

logger = logging.getLogger(__name__)


def register_middleware(app: FastAPI, settings: Settings) -> None:
    """Register request-ID, logging, rate-limit-header, GZip, and CORS middleware (declared inner-first so inbound order is CORS → GZip → request-ID → rate-limit → logging → route)."""

    # The single source of access logs (Uvicorn's is silenced), consistent however the app launches.
    @app.middleware("http")
    async def _log_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # The outer ServerErrorMiddleware handles the exception, so the failed
            # request never reaches the access line below — log here and re-raise.
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
            "%s %s → %d (%.1fms) [rid=%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            getattr(request.state, "request_id", "-"),
        )
        return response

    # Real policy headers on enforced routes; nominal informational headers elsewhere.
    @app.middleware("http")
    async def _rate_limit_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        applied = getattr(request.state, "rate_limit_applied", False)
        policy = getattr(request.state, "rate_limit", None)
        if not applied:
            limit = settings.rate_limit_nominal
            remaining = limit
            reset = int(time.time()) + 60
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset)
        elif policy is not None:
            response.headers["X-RateLimit-Limit"] = str(policy["limit"])
            response.headers["X-RateLimit-Remaining"] = str(policy["remaining"])
            response.headers["X-RateLimit-Reset"] = str(policy["reset"])
        # A metadata-less RateLimitError keeps Retry-After but omits unknown X-RateLimit capacity.
        return response

    # Declared last so it runs earliest inbound, setting request.state.request_id
    # before _log_requests reads it; echoes a caller-supplied id or generates one.
    @app.middleware("http")
    async def _request_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # CORS — wide open for local dev.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_methods,
        allow_headers=settings.cors_headers,
    )
