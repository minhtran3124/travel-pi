"""rate_limit_counters table shape + uniqueness (specs/rate-limit-primitive T1.1).

The alembic upgrade/downgrade round-trip is exercised by the CLI half of the
task Verify command; this test pins the table shape and the unique constraint
that both the migration and ``create_all`` must produce, on a throwaway engine.
"""

import pytest
from app.db.base import Base
from app.db.engine import get_session_factory
from app.db.models import RateLimitCounter
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def session(tmp_path):
    url = f"sqlite:///{tmp_path / 'rl.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(bind=factory().get_bind())
    return factory()


def test_table_registered_with_expected_columns():
    cols = {c.name for c in RateLimitCounter.__table__.columns}
    assert {"bucket", "subject", "window_start", "count", "id"} <= cols


def test_unique_window_constraint_enforced(session):
    session.add(
        RateLimitCounter(bucket="feedback", subject="u1", window_start=100, count=1)
    )
    session.commit()
    session.add(
        RateLimitCounter(bucket="feedback", subject="u1", window_start=100, count=1)
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_different_window_or_subject_is_allowed(session):
    session.add_all(
        [
            RateLimitCounter(
                bucket="feedback", subject="u1", window_start=100, count=1
            ),
            RateLimitCounter(
                bucket="feedback", subject="u1", window_start=160, count=1
            ),
            RateLimitCounter(
                bucket="feedback", subject="u2", window_start=100, count=1
            ),
            RateLimitCounter(bucket="chat", subject="u1", window_start=100, count=1),
        ]
    )
    session.commit()
    assert session.query(RateLimitCounter).count() == 4
