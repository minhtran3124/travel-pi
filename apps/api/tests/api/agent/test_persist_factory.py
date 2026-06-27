"""Regression: the stream persistence factory must preserve DB credentials.

The first implementation derived the isolated sessionmaker from
``str(session.get_bind().url)``. SQLAlchemy masks the password as ``***`` in a
stringified URL, so on Postgres the isolated session authenticated with the
literal password ``***`` and failed (``password authentication failed for user
"travel"``). SQLite has no password, so the original test suite missed it.

``_isolated_factory`` now binds to the request session's *engine* directly — no
URL round-trip — so credentials are preserved. These tests pin that behavior
without needing a live database (``create_engine`` does not connect until used).
"""

from app.routers.agent import _isolated_factory
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_PG_URL = "postgresql+psycopg://travel:s3cret@db:5432/travel"


def test_isolated_factory_binds_to_same_engine():
    engine = create_engine(_PG_URL)  # not connected
    session = sessionmaker(bind=engine)()
    try:
        factory = _isolated_factory(session)
        # Same engine object → identical pool + credentials, no URL parsing.
        assert factory().get_bind() is engine
        assert factory().get_bind().url.password == "s3cret"
    finally:
        session.close()


def test_stringified_url_would_have_masked_password():
    # Documents the original bug: the rejected str(URL) approach loses the
    # password, which is exactly what broke Postgres persistence.
    engine = create_engine(_PG_URL)
    assert "***" in str(engine.url)
    assert "s3cret" not in str(engine.url)
