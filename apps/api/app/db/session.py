"""Request-scoped session dependency: one Session per request, sharing one transaction across repos."""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.engine import get_session_factory


def get_session() -> Iterator[Session]:
    """Yield one request-scoped ``Session``: commit on success, rollback on error, always close."""
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
