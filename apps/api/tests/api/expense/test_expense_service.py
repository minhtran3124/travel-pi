"""Unit tests for ExpenseService — business logic, FX conversion, summaries."""

import pytest
from app.exceptions import NotFoundError
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.schemas.trip import TripCreate
from app.services.expense_service import ExpenseService
from app.services.trip_service import TripService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def svc(seeded_session):
    """ExpenseService bound to the seeded session (FX rates loaded)."""
    return ExpenseService(seeded_session)


@pytest.fixture()
def trip_id(seeded_session):
    """Create a minimal trip and return its ID."""
    trip = TripService(seeded_session).create_trip(TripCreate(title="Test Trip"))
    return trip.id


# ---------------------------------------------------------------------------
# Happy path: create with VND
# ---------------------------------------------------------------------------


def test_create_vnd_expense(svc, trip_id):
    """Creating a VND expense produces a positive amount_usd and fx_rate."""
    expense = svc.create(
        trip_id,
        ExpenseCreate(category="food", amount=100_000, currency="VND"),
    )
    assert expense.currency == "VND"
    assert expense.amount == 100_000
    assert expense.amount_usd > 0
    assert expense.fx_rate > 0
    assert expense.trip_id == trip_id


# ---------------------------------------------------------------------------
# 404: unknown trip
# ---------------------------------------------------------------------------


def test_create_unknown_trip_raises(svc):
    with pytest.raises(NotFoundError, match="not found"):
        svc.create(
            "nonexistent-trip",
            ExpenseCreate(category="food", amount=10.0, currency="USD"),
        )


# ---------------------------------------------------------------------------
# 404: unknown currency
# ---------------------------------------------------------------------------


def test_create_unknown_currency_raises(svc, trip_id):
    with pytest.raises(NotFoundError, match="XYZ"):
        svc.create(
            trip_id,
            ExpenseCreate(category="food", amount=10.0, currency="XYZ"),
        )


# ---------------------------------------------------------------------------
# Summary: totals, by_category, by_currency
# ---------------------------------------------------------------------------


def test_summary_totals_and_breakdown(svc, trip_id):
    """Two expenses → total_usd is their sum; by_category and by_currency correct."""
    svc.create(trip_id, ExpenseCreate(category="food", amount=10.0, currency="USD"))
    svc.create(
        trip_id, ExpenseCreate(category="transport", amount=20.0, currency="USD")
    )

    summary = svc.summary(trip_id)

    assert summary.expense_count == 2
    assert abs(summary.total_usd - 30.0) < 0.01

    cats = {c.category: c for c in summary.by_category}
    assert "food" in cats
    assert "transport" in cats
    assert cats["food"].count == 1
    assert cats["transport"].count == 1

    currs = {c.currency: c for c in summary.by_currency}
    assert "USD" in currs
    assert currs["USD"].count == 2
    assert abs(currs["USD"].total_original - 30.0) < 0.01


# ---------------------------------------------------------------------------
# Budget actuals with no caps
# ---------------------------------------------------------------------------


def test_summary_budget_no_caps(svc, trip_id):
    """With no budget caps set, total_cap and total_remaining are None, over_budget is False."""
    svc.create(trip_id, ExpenseCreate(category="food", amount=50.0, currency="USD"))

    summary = svc.summary(trip_id)

    assert summary.budget.total_cap is None
    assert summary.budget.total_remaining is None
    assert summary.budget.over_budget is False
    assert summary.budget.expense_spent > 0


# ---------------------------------------------------------------------------
# Get non-existent expense
# ---------------------------------------------------------------------------


def test_get_nonexistent_raises(svc, trip_id):
    with pytest.raises(NotFoundError, match="not found"):
        svc.get(trip_id, "nonexistent-expense-id")


# ---------------------------------------------------------------------------
# Update: amount recomputed
# ---------------------------------------------------------------------------


def test_update_amount_recomputes_usd(svc, trip_id):
    """Updating amount should recompute amount_usd and fx_rate."""
    expense = svc.create(
        trip_id,
        ExpenseCreate(category="food", amount=10.0, currency="USD"),
    )
    original_usd = expense.amount_usd

    updated = svc.update(
        trip_id,
        expense.id,
        ExpenseUpdate(amount=50.0),
    )

    assert updated.amount == 50.0
    assert updated.amount_usd != original_usd
    assert abs(updated.amount_usd - 50.0) < 0.01  # USD→USD rate is 1.0
