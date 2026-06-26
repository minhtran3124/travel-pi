"""Unit tests for ExpenseRepository — direct ORM layer, temp SQLite DB."""

import pytest
from app.db.base import Base
from app.db.engine import get_session_factory
from app.repositories.expense import ExpenseRepository
from app.schemas.expense import Expense


def _make_expense(**over) -> Expense:
    """Build a minimal valid Expense for repo.add()."""
    base = {
        "id": "exp-1",
        "trip_id": "trip-abc",
        "category": "food",
        "amount": 10.0,
        "currency": "USD",
        "amount_usd": 10.0,
        "fx_rate": 1.0,
        "description": None,
        "occurred_at": "2026-06-01T12:00:00+00:00",
        "created_at": "2026-06-01T12:00:00+00:00",
    }
    base.update(over)
    return Expense(**base)


@pytest.fixture()
def repo(tmp_path):
    sf = get_session_factory(f"sqlite:///{tmp_path / 'exp.db'}")
    Base.metadata.create_all(sf().get_bind(), checkfirst=True)
    return ExpenseRepository(sf)


# ---------------------------------------------------------------------------
# Happy path: create → get
# ---------------------------------------------------------------------------


def test_add_and_get(repo):
    expense = repo.add(_make_expense(id="e1", description="lunch"))
    fetched = repo.get("e1")
    assert fetched is not None
    assert fetched.id == "e1"
    assert fetched.description == "lunch"
    assert fetched.amount == 10.0


def test_get_missing_returns_none(repo):
    assert repo.get("nonexistent") is None


# ---------------------------------------------------------------------------
# List filters
# ---------------------------------------------------------------------------


def test_list_all_for_trip(repo):
    repo.add(_make_expense(id="e1", trip_id="t1"))
    repo.add(_make_expense(id="e2", trip_id="t1"))
    repo.add(_make_expense(id="e3", trip_id="t2"))
    result = repo.list("t1")
    assert len(result) == 2
    assert all(e.trip_id == "t1" for e in result)


def test_list_category_filter(repo):
    repo.add(_make_expense(id="e1", trip_id="t1", category="food"))
    repo.add(_make_expense(id="e2", trip_id="t1", category="transport"))
    result = repo.list("t1", category="food")
    assert len(result) == 1
    assert result[0].id == "e1"


def test_list_currency_filter(repo):
    repo.add(_make_expense(id="e1", trip_id="t1", currency="USD"))
    repo.add(_make_expense(id="e2", trip_id="t1", currency="EUR"))
    result = repo.list("t1", currency="EUR")
    assert len(result) == 1
    assert result[0].id == "e2"


def test_list_date_from_filter(repo):
    repo.add(
        _make_expense(id="e1", trip_id="t1", occurred_at="2026-05-01T00:00:00+00:00")
    )
    repo.add(
        _make_expense(id="e2", trip_id="t1", occurred_at="2026-06-15T00:00:00+00:00")
    )
    result = repo.list("t1", date_from="2026-06-01")
    assert len(result) == 1
    assert result[0].id == "e2"


def test_list_date_to_filter(repo):
    repo.add(
        _make_expense(id="e1", trip_id="t1", occurred_at="2026-05-01T00:00:00+00:00")
    )
    repo.add(
        _make_expense(id="e2", trip_id="t1", occurred_at="2026-06-15T00:00:00+00:00")
    )
    result = repo.list("t1", date_to="2026-05-31")
    assert len(result) == 1
    assert result[0].id == "e1"


def test_list_date_range_filter(repo):
    repo.add(
        _make_expense(id="e1", trip_id="t1", occurred_at="2026-05-01T00:00:00+00:00")
    )
    repo.add(
        _make_expense(id="e2", trip_id="t1", occurred_at="2026-06-10T00:00:00+00:00")
    )
    repo.add(
        _make_expense(id="e3", trip_id="t1", occurred_at="2026-07-01T00:00:00+00:00")
    )
    result = repo.list("t1", date_from="2026-06-01", date_to="2026-06-30")
    assert len(result) == 1
    assert result[0].id == "e2"


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------


def test_soft_delete_hides_from_get(repo):
    repo.add(_make_expense(id="e1", trip_id="t1"))
    assert repo.soft_delete("e1", when="2026-06-20T00:00:00+00:00") is True
    assert repo.get("e1") is None


def test_soft_delete_hides_from_list(repo):
    repo.add(_make_expense(id="e1", trip_id="t1"))
    repo.add(_make_expense(id="e2", trip_id="t1"))
    repo.soft_delete("e1", when="2026-06-20T00:00:00+00:00")
    result = repo.list("t1")
    assert len(result) == 1
    assert result[0].id == "e2"


def test_soft_delete_missing_returns_false(repo):
    assert repo.soft_delete("nonexistent", when="2026-06-20T00:00:00+00:00") is False


def test_soft_delete_already_deleted_returns_false(repo):
    repo.add(_make_expense(id="e1", trip_id="t1"))
    repo.soft_delete("e1", when="2026-06-20T00:00:00+00:00")
    assert repo.soft_delete("e1", when="2026-06-20T00:00:00+00:00") is False


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_mutates_fields(repo):
    repo.add(_make_expense(id="e1", trip_id="t1", amount=10.0, description="old"))
    updated = repo.update("e1", amount=25.0, description="new")
    assert updated is not None
    assert updated.amount == 25.0
    assert updated.description == "new"
    # Verify the change is persisted
    fetched = repo.get("e1")
    assert fetched.amount == 25.0
    assert fetched.description == "new"


def test_update_missing_returns_none(repo):
    assert repo.update("nonexistent", amount=99.0) is None


def test_update_deleted_returns_none(repo):
    repo.add(_make_expense(id="e1", trip_id="t1"))
    repo.soft_delete("e1", when="2026-06-20T00:00:00+00:00")
    assert repo.update("e1", amount=99.0) is None
