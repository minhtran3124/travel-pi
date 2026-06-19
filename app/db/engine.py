"""Engine + session-factory construction, keyed by connection URL.

The whole point of the DB rewrite: the backend is chosen by the URL, nothing
else. ``get_engine`` is cached per URL so all services/repos share one engine
(and one pool) per database. Tests pass a distinct temp-SQLite URL, which gets
its own cached engine — that is what keeps test data isolated from travel.db.

Sync only: the codebase runs DB work in FastAPI's threadpool (CLAUDE.md
"async only for real network I/O"). No async engine here.
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def _connect_args(url: str) -> dict:
    # SQLite hands a connection to whichever threadpool worker runs the
    # request; allow cross-thread use. Postgres needs no such flag.
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


@lru_cache(maxsize=None)
def get_engine(url: str) -> Engine:
    """Return a process-wide Engine for ``url`` (one per distinct URL)."""
    return create_engine(
        url,
        connect_args=_connect_args(url),
        pool_pre_ping=True,  # drop dead Postgres connections instead of erroring
        future=True,
    )


@lru_cache(maxsize=None)
def get_session_factory(url: str) -> sessionmaker[Session]:
    """Return a sessionmaker bound to the (cached) engine for ``url``."""
    return sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)
