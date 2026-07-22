"""Reusable, DB-backed rate limiter (specs/rate-limit-primitive).

Two entry points over :class:`~app.repositories.rate_limit.RateLimitRepository`:

- :func:`enforce_rate_limit` — the core callable. Resolve the effective subject
  yourself, then call it (used where the subject comes from a request body, e.g.
  the feedback endpoint's anonymous id).
- :func:`rate_limit` — a FastAPI dependency factory sugar over the callable. Its
  default subject resolver limits AUTHENTICATED callers only (anonymous → skipped,
  never trusted via a spoofable query/body id). The resolver is a seam: pass a
  custom one, or an IP-based resolver once a shared cross-worker store exists
  (deferred per-IP hardening).

Enforcement is per effective user; per-IP/device is intentionally out of scope.
"""

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

# Module-level Depends aliases. Defined here (not inline in the nested
# dependency) so FastAPI resolves them correctly under Python 3.14's deferred
# annotations, matching the repo's SessionDep/OptionalUserDep convention.
_SessionDep = Annotated[Session, Depends(get_session)]
_OptionalUserDep = Annotated[AuthUser | None, Depends(get_current_user_optional)]


def _default_subject(request: Request, auth_user: AuthUser | None) -> str | None:
    """Authenticated callers only; anonymous → ``None`` (limit skipped).

    Deliberately does NOT fall back to a client-supplied id (query/body): such an
    id is spoofable and shares the authenticated id space, so trusting it would
    let an anonymous caller both evade the limit (rotate ids) and exhaust another
    user's counter by sending their id (cross-user DoS). Anonymous limiting needs
    a stable, non-spoofable key (per-IP/device) — deferred — so endpoints with
    anonymous principals must pass an explicit ``subject`` resolver that namespaces
    the actor (e.g. feedback's body-resolved effective actor under an ``anon:`` key).
    """
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
    """Cache one sessionmaker per engine (built once, not per request).

    The engine comes from the request session's bind (itself process-cached per
    URL), so this keys on identity and stays a small, bounded cache.
    """
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
    """Record one hit and raise :class:`RateLimitError` (429) when over the limit.

    :param session: The request-scoped session (unit of work). It must not have
        started a transaction yet; the limiter commits on an independent session
        so rejected/erroring requests are still counted durably.
    :param name: Policy/bucket name (e.g. ``"feedback"``).
    :param subject: Effective actor id.
    :param limit: Max requests allowed per window.
    :param window_seconds: Fixed-window length in seconds.
    :param now_epoch: Override the clock (tests); defaults to ``time.time()``.
    :param request: Optional HTTP request. Pass it when calling the core function
        directly from a route so middleware can emit the real policy headers.
    :return: The :class:`RateLimitDecision` when allowed.
    """
    _validate_policy(name, limit, window_seconds)
    # The durable increment must use an independent transaction. If the caller's
    # request session has already started one, a prior SQLite write can hold the
    # database-wide writer lock and make the limiter wait for busy_timeout before
    # failing with an opaque "database is locked" error. Enforce one explicit,
    # cross-engine contract instead: rate limiting runs before any request UoW
    # read/write. Never commit or roll back caller-owned work to make room.
    if session.in_transaction():
        raise RuntimeError(
            "enforce_rate_limit() must run before the request session starts a "
            "transaction; attach the dependency before database work"
        )
    if now_epoch is None:
        now_epoch = int(time.time())
    # Commit the increment in its OWN transaction on the same engine, not the
    # caller's unit of work: an abuse limiter must count a request even when the
    # request later rolls back (a 4xx/5xx after this check). Factory mode gives
    # the repo an own-session + own-commit; the caller's session only supplies
    # the engine bind, so this still targets the request's database (and the
    # test's isolated DB).
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
    """Build a FastAPI dependency enforcing a per-subject fixed-window limit.

    When the resolver yields no subject (anonymous with no fallback id), the
    limit is skipped — the route's own auth is responsible for rejecting it.
    """
    # Fail at wiring/startup, not per-request, on a misconfigured policy
    # (e.g. an env override setting the window to 0 → ZeroDivisionError).
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
