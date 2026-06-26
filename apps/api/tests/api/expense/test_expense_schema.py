"""Unit tests for app/schemas/expense.py — no DB, no HTTP."""

import pytest
from app.enums import ExpenseCategory
from app.schemas.expense import (
    EXPENSE_CODE_PREFIX,
    Expense,
    ExpenseCreate,
    ExpenseUpdate,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_EXPENSE_DATA = {
    "category": ExpenseCategory.FOOD,
    "amount": 12.50,
    "currency": "USD",
}

FULL_EXPENSE_DATA = {
    **VALID_EXPENSE_DATA,
    "id": "abc123",
    "trip_id": "trip456",
    "amount_usd": 12.50,
    "fx_rate": 1.0,
    "created_at": "2024-01-15T10:30:00Z",
}


# ---------------------------------------------------------------------------
# ExpenseCreate — amount validation
# ---------------------------------------------------------------------------


def test_amount_zero_is_rejected():
    with pytest.raises(ValidationError):
        ExpenseCreate(**{**VALID_EXPENSE_DATA, "amount": 0})


def test_amount_negative_is_rejected():
    with pytest.raises(ValidationError):
        ExpenseCreate(**{**VALID_EXPENSE_DATA, "amount": -5.0})


def test_amount_positive_is_accepted():
    schema = ExpenseCreate(**VALID_EXPENSE_DATA)
    assert schema.amount == 12.50


# ---------------------------------------------------------------------------
# ExpenseCreate — currency normalisation
# ---------------------------------------------------------------------------


def test_currency_is_uppercased():
    schema = ExpenseCreate(**{**VALID_EXPENSE_DATA, "currency": "usd"})
    assert schema.currency == "USD"


def test_currency_is_stripped_and_uppercased():
    schema = ExpenseCreate(**{**VALID_EXPENSE_DATA, "currency": " vnd "})
    assert schema.currency == "VND"


def test_currency_already_uppercase_unchanged():
    schema = ExpenseCreate(**{**VALID_EXPENSE_DATA, "currency": "EUR"})
    assert schema.currency == "EUR"


# ---------------------------------------------------------------------------
# Expense — short_code computed field
# ---------------------------------------------------------------------------


def test_short_code_starts_with_exp_prefix():
    expense = Expense(**FULL_EXPENSE_DATA)
    assert expense.short_code.startswith(f"{EXPENSE_CODE_PREFIX}-")


def test_short_code_is_ten_chars():
    expense = Expense(**FULL_EXPENSE_DATA)
    # "EXP-" (4) + 6 chars = 10
    assert len(expense.short_code) == 10


def test_short_code_is_deterministic():
    expense1 = Expense(**FULL_EXPENSE_DATA)
    expense2 = Expense(**FULL_EXPENSE_DATA)
    assert expense1.short_code == expense2.short_code


# ---------------------------------------------------------------------------
# ExpenseUpdate — all-None is valid
# ---------------------------------------------------------------------------


def test_expense_update_all_none_is_valid():
    update = ExpenseUpdate()
    assert update.category is None
    assert update.amount is None
    assert update.currency is None
    assert update.description is None
    assert update.occurred_at is None


def test_expense_update_zero_amount_rejected():
    with pytest.raises(ValidationError):
        ExpenseUpdate(amount=0)


def test_expense_update_currency_normalised():
    update = ExpenseUpdate(currency=" jpy ")
    assert update.currency == "JPY"
