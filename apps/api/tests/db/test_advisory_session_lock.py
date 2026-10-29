"""advisory_session_lock must not take its connection from the request pool and must
never block the event loop on a pool checkout (a sync checkout there froze the loop
and doubled per-turn pool use)."""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest
from app.db import locks
from app.exceptions import ConflictError


def _pg_session(engine: MagicMock) -> MagicMock:
    session = MagicMock()
    bind = session.get_bind.return_value
    bind.dialect.name = "postgresql"
    bind.engine = engine
    engine.url.render_as_string.return_value = "postgresql+psycopg://x/y"
    return session


@pytest.fixture
def lock_engine(monkeypatch):
    """Fake dedicated lock engine; records the thread each connect() ran on."""
    eng = MagicMock()
    eng.threads = []
    conn = eng.connect.return_value.execution_options.return_value
    conn.execute.return_value.scalar.return_value = True

    def _connect():
        eng.threads.append(threading.current_thread())
        return eng.connect.return_value

    eng.connect.side_effect = _connect
    monkeypatch.setattr(locks, "_lock_engine", lambda url: eng)
    eng.conn = conn
    return eng


def test_lock_uses_dedicated_engine_off_event_loop(lock_engine):
    async def _run():
        request_engine = MagicMock()
        session = _pg_session(request_engine)
        async with locks.advisory_session_lock(session, "t", "busy"):
            pass
        request_engine.connect.assert_not_called()  # request pool untouched
        assert lock_engine.threads
        assert lock_engine.threads[0] is not threading.main_thread()
        lock_engine.conn.close.assert_called_once()

    asyncio.run(_run())


def test_lock_conflict_raises_and_closes(lock_engine):
    async def _run():
        lock_engine.conn.execute.return_value.scalar.return_value = False
        with pytest.raises(ConflictError):
            async with locks.advisory_session_lock(
                _pg_session(MagicMock()), "t", "busy"
            ):
                pass
        lock_engine.conn.close.assert_called_once()

    asyncio.run(_run())


def test_lock_noop_off_postgres():
    async def _run():
        session = MagicMock()
        session.get_bind.return_value.dialect.name = "sqlite"
        async with locks.advisory_session_lock(session, "t", "busy"):
            pass

    asyncio.run(_run())
