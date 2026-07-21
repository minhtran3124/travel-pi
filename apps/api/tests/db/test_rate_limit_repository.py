"""RateLimitRepository atomic window increment (specs/rate-limit-primitive T2.1)."""

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import RateLimitCounter
from app.repositories.rate_limit import RateLimitRepository

WINDOW = 60
LIMIT = 3


@pytest.fixture
def repo(tmp_db):
    # Cross-engine: Postgres under TEST_DATABASE_URL, else temp SQLite. Clean the
    # shared table so each test starts empty on the Postgres path.
    factory = get_session_factory(tmp_db)
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    with factory() as s:
        s.query(RateLimitCounter).delete()
        s.commit()
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


def test_prune_does_not_wipe_a_different_bucket_active_window(repo):
    # Reusable across policies with DIFFERENT window lengths: a short-window
    # policy's prune must not delete a long-window policy's still-active row.
    # chat window=3600 at now=10000 -> window_start 7200, active until 10800.
    repo.hit(
        bucket="chat", subject="u1", now_epoch=10000, limit=100, window_seconds=3600
    )
    # feedback window=60 at now=10001 -> its prune cutoff is 9900; the chat row
    # (7200 < 9900) would be wiped by an UNSCOPED prune.
    repo.hit(
        bucket="feedback", subject="u1", now_epoch=10001, limit=3, window_seconds=60
    )
    # Second chat hit lands in the SAME chat window; it must see count=2, proving
    # the feedback prune left the chat counter intact (buggy prune -> count=1).
    d = repo.hit(
        bucket="chat", subject="u1", now_epoch=10002, limit=100, window_seconds=3600
    )
    assert d.remaining == 100 - 2
    with repo._session() as s:
        chat_windows = {
            r.window_start
            for r in s.query(RateLimitCounter).filter_by(bucket="chat").all()
        }
    assert chat_windows == {7200}


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
