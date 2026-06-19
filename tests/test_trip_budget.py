"""API + enum tests for per-category trip budgets (specs/trip-budget)."""

from app.enums import BudgetCategory


def test_budget_category_values():
    assert {c.value for c in BudgetCategory} == {
        "flights",
        "hotels",
        "activities",
        "buffer",
    }


def test_trip_budget_schema_shape():
    from app.schemas.trip import (
        BudgetCategories,
        CategoryBudget,
        TripBudget,
        TripBudgetSet,
    )

    cat = CategoryBudget(cap=700.0, spent=600.0, remaining=100.0)
    cats = BudgetCategories(flights=cat, hotels=cat, activities=cat, buffer=cat)
    budget = TripBudget(
        trip_id="t1",
        categories=cats,
        total_cap=2800.0,
        total_spent=2400.0,
        total_remaining=400.0,
        over_budget=False,
    )
    assert budget.categories.flights.remaining == 100.0
    # POST body: all caps optional, negative rejected
    assert TripBudgetSet(flights=700).flights == 700
    assert TripBudgetSet().flights is None
