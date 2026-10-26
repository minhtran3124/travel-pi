"""Engine + session-factory construction, cached per connection URL so each URL gets one shared engine and pool."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _connect_args(url: str) -> dict:
    # SQLite connection may cross threadpool workers; allow cross-thread use.
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


@lru_cache(maxsize=None)  # noqa: UP033 — process-wide engine cache, one per URL
def get_engine(url: str) -> Engine:
    """Return a process-wide Engine for ``url`` (one per distinct URL)."""
    kwargs: dict = {}
    if not url.startswith("sqlite"):
        # SQLite uses its own pool class; sizing only applies to server databases.
        settings = get_settings()
        kwargs = {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_timeout": settings.db_pool_timeout,
        }
    return create_engine(
        url,
        connect_args=_connect_args(url),
        pool_pre_ping=True,  # drop dead Postgres connections instead of erroring
        future=True,
        **kwargs,
    )


@lru_cache(maxsize=None)  # noqa: UP033 — shares the cached engine for this URL
def get_session_factory(url: str) -> sessionmaker[Session]:
    """Return a sessionmaker bound to the (cached) engine for ``url``."""
    return sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)
