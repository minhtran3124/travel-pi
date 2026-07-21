"""RateLimitRepository atomic window increment (specs/rate-limit-primitive T2.1)."""

import pytest
from app.db.base import Base
from app.db.engine import get_session_factory
from app.db.models import RateLimitCounter
from app.repositories.rate_limit import RateLimitRepository

WINDOW = 60
LIMIT = 3


@pytest.fixture
def repo(tmp_path):
    url = f"sqlite:///{tmp_path / 'rl.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(bind=factory().get_bind())
    return RateLimitRepository(factory)


def _hit(repo, subject="u1", now=1000, bucket="feedback"):
    return repo.hit(
        bucket=bucket,
        subject=subject,
        now_epoch=now,
        limit=LIMIT,
        window_seconds=WINDOW,
    )


def test_allows_up_to_limit_then_blocks(repo):
    # now=1000 -> window_start = 1000 - (1000 % 60) = 960, reset = 1020
    results = [_hit(repo) for _ in range(LIMIT)]
    assert all(r.allowed for r in results)
    assert [r.remaining for r in results] == [2, 1, 0]
    assert all(r.reset_at == 1020 for r in results)

    blocked = _hit(repo)
    assert blocked.allowed is False
    assert blocked.remaining == 0
    assert blocked.retry_after == 1020 - 1000  # 20s to window reset


def test_window_reset_allows_again(repo):
    for _ in range(LIMIT):
        _hit(repo, now=1000)
    assert _hit(repo, now=1000).allowed is False
    # Next window (>= 1020) starts fresh.
    fresh = _hit(repo, now=1025)
    assert fresh.allowed is True
    assert fresh.remaining == LIMIT - 1


def test_subjects_are_independent(repo):
    for _ in range(LIMIT):
        assert _hit(repo, subject="u1").allowed is True
    # u2 is unaffected by u1 exhausting its window.
    assert _hit(repo, subject="u2").allowed is True


def test_buckets_are_independent(repo):
    for _ in range(LIMIT):
        _hit(repo, bucket="feedback")
    assert _hit(repo, bucket="feedback").allowed is False
    assert _hit(repo, bucket="chat").allowed is True


def test_expired_windows_are_pruned(repo):
    # Fill an old window.
    for _ in range(LIMIT):
        _hit(repo, now=1000)  # window 960
    # A hit in a much later window prunes the elapsed one.
    _hit(repo, now=5000)  # window 4980
    with repo._session() as s:
        windows = {r.window_start for r in s.query(RateLimitCounter).all()}
    assert 960 not in windows
    assert 4980 in windows
