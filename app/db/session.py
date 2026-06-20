"""Request-scoped session dependency (unit-of-work).

``get_session`` is the single seam the rest of the app resolves a database
session through: one ``Session`` per request, committed if the handler returns
cleanly and rolled back if it raises. Repos/services take this session via
``Depends`` instead of binding ``get_settings().database_url`` at import time —
so a request that touches several repos shares one transaction, and tests
override exactly one dependency (``get_session``) instead of repointing module
globals.

Sync only, mirroring ``engine.py``: FastAPI runs sync handlers in a threadpool,
so a plain generator dependency is the right shape (no async engine here).
"""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.engine import get_session_factory


def get_session() -> Iterator[Session]:
    """Yield one request-scoped ``Session`` (commit on success, rollback on error).

    FastAPI dependency: the session is committed when the handler returns
    normally, rolled back if it raises, and always closed. Using one session for
    the whole request makes multi-step writes atomic.
    """
    factory = get_session_factory(get_settings().database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
