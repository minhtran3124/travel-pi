"""RateLimitRepository atomic window increment (specs/rate-limit-primitive T2.1)."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import RateLimitCounter
from app.repositories.rate_limit import RateLimitRepository

WINDOW = 60
LIMIT = 3


@pytest.fixture
def rate_limit_factory(tmp_db):
    # Clean the shared table so each test starts empty on the Postgres path.
    factory = get_session_factory(tmp_db)
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    with factory() as s:
        s.query(RateLimitCounter).delete()
        s.commit()
    return factory


@pytest.fixture
def repo(rate_limit_factory):
    return RateLimitRepository(rate_limit_factory)


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
    assert _hit(repo, subject="u2").allowed is True


def test_buckets_are_independent(repo):
    for _ in range(LIMIT):
        _hit(repo, bucket="feedback")
    assert _hit(repo, bucket="feedback").allowed is False
    assert _hit(repo, bucket="chat").allowed is True


def test_window_size_is_part_of_policy_identity_and_prune_uses_row_expiry(repo):
    # Same-name policies stay distinct: the short window's prune must use the persisted long row's own expiry (10800), not the incoming 60s cutoff.
    repo.hit(
        bucket="feedback",
        subject="u1",
        now_epoch=10000,
        limit=100,
        window_seconds=3600,
    )
    repo.hit(
        bucket="feedback", subject="u1", now_epoch=10001, limit=3, window_seconds=60
    )
    d = repo.hit(
        bucket="feedback",
        subject="u1",
        now_epoch=10002,
        limit=100,
        window_seconds=3600,
    )
    assert d.remaining == 100 - 2
    with repo._session() as s:
        identities = {
            (r.window_seconds, r.window_start, r.count)
            for r in s.query(RateLimitCounter).filter_by(bucket="feedback").all()
        }
    assert identities == {(60, 9960, 1), (3600, 7200, 2)}


def test_expired_windows_are_pruned(repo):
    for _ in range(LIMIT):
        _hit(repo, now=1000)  # window 960
    # A hit in a much later window prunes the elapsed one.
    _hit(repo, now=5000)  # window 4980
    with repo._session() as s:
        windows = {r.window_start for r in s.query(RateLimitCounter).all()}
    assert 960 not in windows
    assert 4980 in windows


def test_one_window_clock_skew_does_not_delete_current_policy_row(repo):
    # Worker B's clock is one window ahead (1020); pruning must retain A's window 960 for its full grace so A's next hit sees count=2.
    first = _hit(repo, now=1000)
    assert first.remaining == LIMIT - 1

    _hit(repo, now=1060)

    current = _hit(repo, now=1001)
    assert current.remaining == LIMIT - 2
    with repo._session() as session:
        rows = {
            (row.window_seconds, row.window_start, row.prune_after, row.count)
            for row in session.query(RateLimitCounter).all()
        }
    assert rows == {(WINDOW, 960, 1080, 2), (WINDOW, 1020, 1140, 1)}


def _synchronized_hit(factory, barrier, *, now, limit=LIMIT):
    # A caller-owned Session proves workers don't share an identity map/transaction; commit at the simulated request boundary.
    with factory() as session:
        barrier.wait(timeout=10)
        decision = RateLimitRepository(session).hit(
            bucket="feedback",
            subject="concurrent-user",
            now_epoch=now,
            limit=limit,
            window_seconds=WINDOW,
        )
        session.commit()
        return decision


def _run_synchronized_hits(factory, *, count, now, limit=LIMIT):
    barrier = Barrier(count)
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [
            pool.submit(_synchronized_hit, factory, barrier, now=now, limit=limit)
            for _ in range(count)
        ]
        return [future.result(timeout=15) for future in futures]


def test_concurrent_first_hit_persists_once_per_distinct_session(rate_limit_factory):
    hit_count = 8
    decisions = _run_synchronized_hits(
        rate_limit_factory, count=hit_count, now=1000, limit=hit_count
    )

    assert all(decision.allowed for decision in decisions)
    with rate_limit_factory() as session:
        rows = session.query(RateLimitCounter).all()
        assert len(rows) == 1
        assert rows[0].count == hit_count


def test_concurrent_existing_row_allows_exactly_limit(rate_limit_factory):
    # Race distinct sessions across the boundary from a seeded row: total allowed must stay exactly LIMIT.
    first = RateLimitRepository(rate_limit_factory).hit(
        bucket="feedback",
        subject="concurrent-user",
        now_epoch=1000,
        limit=LIMIT,
        window_seconds=WINDOW,
    )
    assert first.allowed is True

    concurrent_count = 8
    decisions = _run_synchronized_hits(
        rate_limit_factory, count=concurrent_count, now=1000
    )

    assert 1 + sum(decision.allowed for decision in decisions) == LIMIT
    with rate_limit_factory() as session:
        row = session.query(RateLimitCounter).one()
        assert row.count == concurrent_count + 1
