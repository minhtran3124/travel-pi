"""Transaction-scoped advisory locking, shared by every serialize-a-check-then-write
path (bookings gh-198, trip research B3).

One mechanism, one key hasher: a caller-owned transaction takes a per-subject
``pg_advisory_xact_lock`` so a duplicate check and its insert are atomic against a
concurrent request for the same subject. The lock releases automatically when that
transaction commits or rolls back. A no-op off Postgres (SQLite has no advisory
locks), so the guard degrades to the plain sequential check the unit suite covers.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

import anyio
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.exceptions import ConflictError


def advisory_lock_key(name: str) -> int:
    """Hash a subject name to a stable signed int64 lock key. blake2b (not the
    salted builtin ``hash()``) keeps the key identical across processes, so two
    workers contending for the same subject take the same lock."""
    digest = hashlib.blake2b(name.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def advisory_xact_lock(session: Session, name: str) -> None:
    """Take a transaction-scoped advisory lock keyed by *name* on *session*'s
    current transaction (blocks until granted). No-op off Postgres. The caller
    must own the transaction so the lock spans the check and the write and is
    released on commit/rollback."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": advisory_lock_key(name)},
        )


@lru_cache(maxsize=None)  # noqa: UP033 — process-wide lock engine, one per URL
def _lock_engine(url: str) -> Engine:
    """A small dedicated engine for session-lock connections, so a held lock never
    takes a slot from the request pool (which would double per-turn pool use and let
    lock holders starve the request sessions)."""
    settings = get_settings()
    return create_engine(
        url,
        pool_size=settings.db_lock_pool_size,
        max_overflow=0,
        pool_timeout=settings.db_pool_timeout,
        pool_pre_ping=True,
        future=True,
    )


@asynccontextmanager
async def advisory_session_lock(
    session: Session, name: str, detail: str
) -> AsyncIterator[None]:
    """Hold a non-blocking *session-level* advisory lock keyed by *name* for the
    ``async with`` body; raise ``ConflictError(detail)`` (409) if another holder has it.

    Unlike ``advisory_xact_lock`` this survives the caller's commits (``agent_chat``
    commits mid-turn): it lives on its own autocommit connection from a dedicated
    lock engine (``db_lock_pool_size`` connections per process, separate from the
    request pool), unlocked, then closed, in ``finally`` (closing the connection also
    drops the lock should the explicit unlock fail). Every blocking DB call runs in
    the threadpool so a pool wait never stalls the event loop. No-op off Postgres."""
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return
    key = advisory_lock_key(name)
    url = bind.engine.url.render_as_string(hide_password=False)
    conn = await run_in_threadpool(
        lambda: (
            _lock_engine(url).connect().execution_options(isolation_level="AUTOCOMMIT")
        )
    )
    try:
        got = await run_in_threadpool(
            lambda: conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
            ).scalar()
        )
        if not got:
            raise ConflictError(detail)
        try:
            yield
        finally:
            # Shielded: a client-disconnect cancellation must not skip the unlock/close.
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(
                    lambda: conn.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": key}
                    )
                )
    finally:
        with anyio.CancelScope(shield=True):
            await run_in_threadpool(conn.close)
