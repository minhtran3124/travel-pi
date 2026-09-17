"""Reusable, DB-backed per-user fixed-window rate limiter over :class:`~app.repositories.rate_limit.RateLimitRepository` (per-IP/device intentionally out of scope)."""

import time
from collections.abc import Callable
from functools import cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import AuthUser, get_current_user_optional
from app.db.session import get_session
from app.exceptions import RateLimitError
from app.repositories.rate_limit import RateLimitDecision, RateLimitRepository

SubjectResolver = Callable[[Request, AuthUser | None], str | None]

# Module-level Depends aliases so FastAPI resolves them under Python 3.14 deferred annotations.
_SessionDep = Annotated[Session, Depends(get_session)]
_OptionalUserDep = Annotated[AuthUser | None, Depends(get_current_user_optional)]


def _default_subject(request: Request, auth_user: AuthUser | None) -> str | None:
    """Authenticated callers only; anonymous → ``None`` (limit skipped). A client-supplied id is spoofable and shares the auth id space, so it's never trusted — anonymous endpoints must pass an explicit namespaced ``subject`` resolver."""
    return auth_user.id if auth_user is not None else None


def _validate_policy(name: str, limit: int, window_seconds: int) -> None:
    """Reject a misconfigured policy early (a 0 window would ZeroDivisionError)."""
    if limit <= 0 or window_seconds <= 0:
        raise ValueError(
            f"rate limit policy '{name}' requires positive limit and window; "
            f"got limit={limit}, window_seconds={window_seconds}"
        )


@cache
def _independent_factory(engine: Engine) -> sessionmaker[Session]:
    """Cache one sessionmaker per engine (keyed on the process-cached engine identity)."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def enforce_rate_limit(
    session: Session,
    *,
    name: str,
    subject: str,
    limit: int,
    window_seconds: int,
    now_epoch: int | None = None,
    request: Request | None = None,
) -> RateLimitDecision:
    """Record one hit and raise :class:`RateLimitError` (429) when over the limit; ``session`` must not have started a transaction yet, since the limiter commits on an independent session."""
    _validate_policy(name, limit, window_seconds)
    # Increment in an independent transaction: a caller-owned SQLite tx could
    # hold the writer lock and make the limiter wait, so rate limiting must run
    # before any request UoW read/write.
    if session.in_transaction():
        raise RuntimeError(
            "enforce_rate_limit() must run before the request session starts a "
            "transaction; attach the dependency before database work"
        )
    if now_epoch is None:
        now_epoch = int(time.time())
    # Commit on the same engine as the caller but in its own session/transaction,
    # so the hit counts even when the request later rolls back (a 4xx/5xx).
    factory = _independent_factory(session.get_bind())
    decision = RateLimitRepository(factory).hit(
        bucket=name,
        subject=subject,
        now_epoch=now_epoch,
        limit=limit,
        window_seconds=window_seconds,
    )
    if request is not None:
        request.state.rate_limit_applied = True
        request.state.rate_limit = {
            "limit": limit,
            "remaining": decision.remaining,
            "reset": decision.reset_at,
        }
    if not decision.allowed:
        raise RateLimitError(
            retry_after=decision.retry_after,
            limit=limit,
            remaining=decision.remaining,
            reset_at=decision.reset_at,
            hint="Wait for the Retry-After window, then retry.",
        )
    return decision


def rate_limit(
    *,
    name: str,
    limit: int,
    window_seconds: int,
    subject: SubjectResolver = _default_subject,
) -> Callable[..., None]:
    """Build a FastAPI dependency enforcing a per-subject fixed-window limit; no resolved subject → limit skipped."""
    # Fail at startup, not per-request, on a misconfigured policy.
    _validate_policy(name, limit, window_seconds)

    def dependency(
        request: Request,
        session: _SessionDep,
        auth_user: _OptionalUserDep,
    ) -> None:
        subj = subject(request, auth_user)
        if subj is None:
            return
        enforce_rate_limit(
            session,
            name=name,
            subject=subj,
            limit=limit,
            window_seconds=window_seconds,
            request=request,
        )

    return dependency
