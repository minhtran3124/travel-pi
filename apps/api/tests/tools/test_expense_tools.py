"""Tests for expense_tools' args_schema (specs/standardize-tool-args-schema Task 1.3)."""

import json

import pytest
from app.tools.expense_tools import (
    AddExpenseArgs,
    ExpenseSummaryArgs,
    ListExpensesArgs,
    add_expense,
    expense_summary,
    list_expenses,
)
from pydantic import ValidationError

CATEGORY_VALUES = [
    "food",
    "transport",
    "accommodation",
    "activities",
    "shopping",
    "entertainment",
    "health",
    "other",
]


def test_all_expense_tools_have_args_schema():
    assert add_expense.args_schema is AddExpenseArgs
    assert list_expenses.args_schema is ListExpensesArgs
    assert expense_summary.args_schema is ExpenseSummaryArgs


def test_add_expense_schema_lists_all_category_values():
    schema_json = json.dumps(add_expense.get_input_schema().model_json_schema())
    for value in CATEGORY_VALUES:
        assert value in schema_json


def test_add_expense_schema_amount_has_positive_constraint():
    schema = add_expense.get_input_schema().model_json_schema()
    amount_schema = schema["properties"]["amount"]
    assert amount_schema.get("exclusiveMinimum") == 0


def test_add_expense_invalid_category_raises_on_invoke():
    with pytest.raises(ValidationError):
        add_expense.invoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": "add_expense",
                "args": {
                    "trip_id": "TRP-0001",
                    "category": "not-a-category",
                    "amount": 10.0,
                    "currency": "USD",
                },
            }
        )


def test_add_expense_invalid_amount_raises_on_invoke():
    with pytest.raises(ValidationError):
        add_expense.invoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": "add_expense",
                "args": {
                    "trip_id": "TRP-0001",
                    "category": "food",
                    "amount": -5.0,
                    "currency": "USD",
                },
            }
        )
