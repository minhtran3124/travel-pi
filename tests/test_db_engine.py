"""Engine/session-factory behavior: dual-URL selection + isolation."""

import pytest
from sqlalchemy import text
from app.db.engine import get_engine, get_session_factory


def test_sqlite_url_builds_sqlite_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    engine = get_engine(url)
    assert engine.dialect.name == "sqlite"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_same_url_returns_same_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'b.db'}"
    assert get_engine(url) is get_engine(url)  # cached


def test_distinct_urls_isolate(tmp_path):
    e1 = get_engine(f"sqlite:///{tmp_path / 'c.db'}")
    e2 = get_engine(f"sqlite:///{tmp_path / 'd.db'}")
    assert e1 is not e2


def test_session_factory_yields_working_session(tmp_path):
    sf = get_session_factory(f"sqlite:///{tmp_path / 'e.db'}")
    with sf() as s:
        assert s.execute(text("SELECT 1")).scalar() == 1
