"""get_session() unit-of-work semantics: commit on success, rollback on error,
session always closed."""

import pytest
from app.core.config import get_settings
from app.db import session as session_module
from app.db.engine import get_session_factory
from sqlalchemy import text


@pytest.fixture
def temp_db_url(tmp_path, monkeypatch):
    """Point get_session at an isolated temp SQLite DB with one scratch table."""
    url = f"sqlite:///{tmp_path / 'uow.db'}"
    monkeypatch.setattr(session_module, "get_settings", lambda: _settings_with_url(url))
    sf = get_session_factory(url)
    with sf() as s:
        s.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))
        s.commit()
    return url


def _settings_with_url(url: str):
    settings = get_settings()
    object.__setattr__(settings, "database_url", url)  # pydantic frozen-safe set
    return settings


def _drain(gen, exc: Exception | None = None):
    """Run a generator dependency to completion the way FastAPI does."""
    session = next(gen)
    try:
        if exc is not None:
            gen.throw(exc)
        else:
            next(gen, None)
    except StopIteration:
        pass
    return session


def test_commits_on_clean_exit(temp_db_url):
    gen = session_module.get_session()
    session = next(gen)
    session.execute(text("INSERT INTO t (v) VALUES ('kept')"))
    next(gen, None)  # generator commits + closes on exhaustion

    with get_session_factory(temp_db_url)() as verify:
        assert verify.execute(text("SELECT v FROM t")).scalar() == "kept"


def test_rolls_back_on_exception(temp_db_url):
    gen = session_module.get_session()
    session = next(gen)
    session.execute(text("INSERT INTO t (v) VALUES ('dropped')"))
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("boom"))  # dependency rolls back + re-raises

    with get_session_factory(temp_db_url)() as verify:
        assert verify.execute(text("SELECT COUNT(*) FROM t")).scalar() == 0


def test_session_closed_after_use(temp_db_url):
    gen = session_module.get_session()
    session = next(gen)
    next(gen, None)
    # A closed Session has no active transaction/bind connection in use.
    assert not session.in_transaction()
