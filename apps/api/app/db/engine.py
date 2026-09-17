"""Engine + session-factory construction, cached per connection URL so each URL gets one shared engine and pool."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def _connect_args(url: str) -> dict:
    # SQLite connection may cross threadpool workers; allow cross-thread use.
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


@lru_cache(maxsize=None)  # noqa: UP033 — process-wide engine cache, one per URL
def get_engine(url: str) -> Engine:
    """Return a process-wide Engine for ``url`` (one per distinct URL)."""
    return create_engine(
        url,
        connect_args=_connect_args(url),
        pool_pre_ping=True,  # drop dead Postgres connections instead of erroring
        future=True,
    )


@lru_cache(maxsize=None)  # noqa: UP033 — shares the cached engine for this URL
def get_session_factory(url: str) -> sessionmaker[Session]:
    """Return a sessionmaker bound to the (cached) engine for ``url``."""
    return sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)
