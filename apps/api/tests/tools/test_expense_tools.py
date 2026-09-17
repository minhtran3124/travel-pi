"""expense_tools argument-schema tests.

An explicit ``args_schema=`` that omits an ``InjectedState`` argument silently
breaks ToolNode injection, so arguments are described inline instead.
"""

import json

import pytest
from app.tools.expense_tools import (
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


def test_all_expense_tools_expose_a_model_facing_schema():
    """Each tool advertises its arguments but hides the injected owner user_id."""
    for tool in (add_expense, list_expenses, expense_summary):
        props = tool.tool_call_schema.model_json_schema()["properties"]
        assert "trip_id" in props, f"{tool.name} must take a trip_id"
        assert "user_id" not in props, f"{tool.name} leaks the injected owner"


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
                    "user_id": "test-user-1",
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
                    "user_id": "test-user-1",
                    "category": "food",
                    "amount": -5.0,
                    "currency": "USD",
                },
            }
        )
