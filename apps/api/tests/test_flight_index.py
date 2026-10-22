"""Regression tests for FlightIndexRepository.remember_many concurrency safety."""

import threading

from app.db.engine import get_session_factory
from app.repositories.flight import FlightIndexRepository
from sqlalchemy import text


def _repo(tmp_path, name: str = "x") -> FlightIndexRepository:
    repo = FlightIndexRepository(get_session_factory(f"sqlite:///{tmp_path}/{name}.db"))
    repo.init_db()
    return repo


def test_remember_many_concurrent_same_batch(tmp_path):
    """Two threads recording the same not-yet-indexed batch concurrently must not raise."""
    repo = _repo(tmp_path, "concurrent")
    # WAL lets a second connection proceed during the first's write txn, surfacing the race.
    with repo._sf() as s:  # noqa: SLF001 — test needs the raw connection
        s.execute(text("PRAGMA journal_mode=WAL"))
        s.commit()

    batch = [
        ("F1", "SGN", "HAN", "2026-07-01"),
        ("F2", "SGN", "HAN", "2026-07-01"),
        ("F3", "SGN", "HAN", "2026-07-01"),
    ]
    n = 8
    barrier = threading.Barrier(n)
    errors: list[BaseException] = []

    def worker() -> None:
        barrier.wait()
        try:
            repo.remember_many(batch)
        except BaseException as exc:  # noqa: BLE001 — capture for assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"remember_many raised under concurrency: {errors!r}"
    for fid in ("F1", "F2", "F3"):
        assert repo.lookup(fid) == ("SGN", "HAN", "2026-07-01")


def test_remember_many_overlapping_batches_is_idempotent(tmp_path):
    """Two batches sharing flight_ids must not raise; index = the union."""
    repo = _repo(tmp_path, "overlap")
    batch_a = [
        ("F1", "SGN", "HAN", "2026-07-01"),
        ("F2", "SGN", "HAN", "2026-07-01"),
    ]
    batch_b = [
        ("F2", "SGN", "HAN", "2026-07-01"),
        ("F3", "SGN", "HAN", "2026-07-01"),
    ]

    repo.remember_many(batch_a)
    repo.remember_many(batch_b)

    assert repo.lookup("F1") == ("SGN", "HAN", "2026-07-01")
    assert repo.lookup("F2") == ("SGN", "HAN", "2026-07-01")
    assert repo.lookup("F3") == ("SGN", "HAN", "2026-07-01")


def test_remember_many_batch_includes_existing_id(tmp_path):
    """A batch re-including a persisted id plus new ids must not raise."""
    repo = _repo(tmp_path, "existing")
    repo.remember_many([("F1", "SGN", "HAN", "2026-07-01")])

    repo.remember_many(
        [
            ("F1", "SGN", "HAN", "2026-07-01"),
            ("F2", "DAD", "HAN", "2026-07-02"),
            ("F3", "DAD", "HAN", "2026-07-02"),
        ]
    )

    assert repo.lookup("F1") == ("SGN", "HAN", "2026-07-01")
    assert repo.lookup("F2") == ("DAD", "HAN", "2026-07-02")
    assert repo.lookup("F3") == ("DAD", "HAN", "2026-07-02")


def test_remember_many_empty_is_noop(tmp_path):
    repo = _repo(tmp_path, "empty")
    repo.remember_many([])
    assert repo.lookup("nope") is None
