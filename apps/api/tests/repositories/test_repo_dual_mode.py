"""Repo base dual-mode contract: a ``sessionmaker`` commits standalone; a live ``Session`` only flushes, deferring the commit to the request boundary."""

from app.db.engine import get_session_factory
from app.repositories.base import Repo
from sqlalchemy import text


class _ScratchRepo(Repo):
    """Minimal repo exercising _session() + _commit() over a scratch table."""

    def write(self, v: str) -> None:
        with self._session() as s:
            s.execute(text("INSERT INTO t (v) VALUES (:v)"), {"v": v})
            self._commit(s)

    def count(self) -> int:
        with self._session() as s:
            return s.execute(text("SELECT COUNT(*) FROM t")).scalar()


def _scratch_factory(tmp_path):
    sf = get_session_factory(f"sqlite:///{tmp_path / 'dual.db'}")
    with sf() as s:
        s.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))
        s.commit()
    return sf


def test_factory_mode_commits_per_operation(tmp_path):
    sf = _scratch_factory(tmp_path)
    _ScratchRepo(sf).write("a")
    # A brand-new session sees it → the write committed standalone.
    assert _ScratchRepo(sf).count() == 1


def test_session_mode_defers_commit(tmp_path):
    sf = _scratch_factory(tmp_path)
    with sf() as live:
        repo = _ScratchRepo(live)
        repo.write("b")
        assert repo.count() == 1  # visible within the unit-of-work (flushed)
        live.rollback()  # request boundary could roll back instead of commit
    # The rollback discarded it → nothing was committed by the repo itself.
    assert _ScratchRepo(sf).count() == 0


def test_session_mode_does_not_close_caller_session(tmp_path):
    sf = _scratch_factory(tmp_path)
    with sf() as live:
        repo = _ScratchRepo(live)
        repo.write("c")
        # _session() hands back the caller's session without closing it, so further work still succeeds.
        repo.write("d")
        live.commit()
    assert _ScratchRepo(sf).count() == 2
