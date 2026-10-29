"""Multi-worker gunicorn: two workers seed at once; the loser's IntegrityError must not abort startup."""

import pytest
from app.core import lifespan as lifespan_mod
from sqlalchemy.exc import IntegrityError


def _integrity_error() -> IntegrityError:
    return IntegrityError(
        "INSERT", {}, Exception("UNIQUE constraint failed: countries.name")
    )


def test_seed_retries_after_concurrent_worker_race(monkeypatch):
    calls = []

    def flaky_seed(_factory):
        calls.append(1)
        if len(calls) == 1:
            raise _integrity_error()

    monkeypatch.setattr(lifespan_mod, "seed_all", flaky_seed)
    lifespan_mod._seed_reference_data(object())
    assert len(calls) == 2


def test_seed_gives_up_on_persistent_integrity_error(monkeypatch):
    def always_fail(_factory):
        raise _integrity_error()

    monkeypatch.setattr(lifespan_mod, "seed_all", always_fail)
    with pytest.raises(IntegrityError):
        lifespan_mod._seed_reference_data(object())
