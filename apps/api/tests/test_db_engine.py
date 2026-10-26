"""Engine/session-factory behavior: dual-URL selection + isolation."""

from app.db.engine import get_engine, get_session_factory
from sqlalchemy import text


def test_sqlite_url_builds_sqlite_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    engine = get_engine(url)
    assert engine.dialect.name == "sqlite"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_same_url_returns_same_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'b.db'}"
    assert get_engine(url) is get_engine(url)


def test_distinct_urls_isolate(tmp_path):
    e1 = get_engine(f"sqlite:///{tmp_path / 'c.db'}")
    e2 = get_engine(f"sqlite:///{tmp_path / 'd.db'}")
    assert e1 is not e2


def test_postgres_engine_uses_configured_pool(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("DB_POOL_SIZE", "3")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "2")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "7")
    get_settings.cache_clear()
    try:
        # create_engine is lazy: no Postgres server is needed to inspect the pool.
        engine = get_engine("postgresql+psycopg://u:p@localhost:5432/pool_cfg_test")
        pool = engine.pool
        assert pool.size() == 3
        assert pool._max_overflow == 2
        assert pool.timeout() == 7
    finally:
        get_settings.cache_clear()


def test_postgres_engine_default_pool_sizes():
    engine = get_engine("postgresql+psycopg://u:p@localhost:5432/pool_default_test")
    assert (engine.pool.size(), engine.pool._max_overflow, engine.pool.timeout()) == (
        5,
        5,
        30,
    )


def test_session_factory_yields_working_session(tmp_path):
    sf = get_session_factory(f"sqlite:///{tmp_path / 'e.db'}")
    with sf() as s:
        assert s.execute(text("SELECT 1")).scalar() == 1
