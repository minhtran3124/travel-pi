"""Shared repo base: dual-mode session binding (factory OR live Session).

Part of the DI/session refactor (``specs/di-session-refactor``). A repo accepts
**either**:

- a legacy ``sessionmaker`` — each method opens and commits its own session
  (the original behavior), or
- a live request-scoped ``Session`` — the unit-of-work (``app.db.session``) owns
  the transaction, so repos *flush* instead of *commit* and never close it.

This bridge lets callers migrate incrementally while the suite stays green; once
every caller passes a ``Session`` the factory branch (and this dual-mode shim)
is removed in the final wave.
"""

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
        """Yield a usable session for one operation.

        Live-session mode: hand back the caller-owned session (do **not** close
        it — the request boundary does). Factory mode: open a fresh session and
        close it at block exit (legacy self-managed behavior).
        """
        if self._s is not None:
            yield self._s
        else:
            with self._sf() as s:
                yield s

    def _commit(self, s: Session) -> None:
        """Persist the current operation.

        Factory mode: ``commit`` — the operation is standalone. Live-session
        mode: ``flush`` only, so integrity errors still surface here while the
        actual commit is deferred to the request boundary (atomic unit-of-work).
        """
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
