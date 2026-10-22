"""Repo base: accepts a live request-scoped Session (flush) or a sessionmaker (commit)."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker


class Repo:
    """Base for SQLAlchemy repos that accept a ``Session`` or a ``sessionmaker``."""

    def __init__(self, session_or_factory: "Session | sessionmaker[Session]") -> None:
        if isinstance(session_or_factory, Session):
            self._s: Session | None = session_or_factory
            self._sf: sessionmaker[Session] | None = None
        else:
            self._s = None
            self._sf = session_or_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        """Live mode yields the caller-owned session (not closed here); factory mode opens/closes a fresh one."""
        if self._s is not None:
            yield self._s
        else:
            with self._sf() as s:
                yield s

    def _commit(self, s: Session) -> None:
        """Flush in live mode so integrity errors still surface here while commit defers to the request boundary; commit in factory mode."""
        if self._s is not None:
            s.flush()
        else:
            s.commit()

    def _bind(self):
        """Return the engine bind for DDL (``create_all``)."""
        if self._s is not None:
            return self._s.get_bind()
        with self._sf() as s:
            return s.get_bind()
