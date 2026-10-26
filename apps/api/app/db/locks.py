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
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

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


@contextmanager
def advisory_session_lock(session: Session, name: str, detail: str) -> Iterator[None]:
    """Hold a non-blocking *session-level* advisory lock keyed by *name* for the
    ``with`` body; raise ``ConflictError(detail)`` (409) if another holder has it.

    Unlike ``advisory_xact_lock`` this survives the caller's commits (``agent_chat``
    commits mid-turn): it lives on its own autocommit connection, taken from the
    session's engine and unlocked, then closed, in ``finally`` (closing the
    connection also drops the lock should the explicit unlock fail). No-op off
    Postgres. Costs one extra pooled connection for the duration of the body."""
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return
    key = advisory_lock_key(name)
    conn = bind.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        if not conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
        ).scalar():
            raise ConflictError(detail)
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    finally:
        conn.close()
