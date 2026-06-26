"""Expense / budget tools (specs/travel-agent Task 3.4).

Wrap ``ExpenseService`` for the budget sub-agent: record spend, list it, and roll
it up. Pairs with ``get_trip_budget`` (trip_tools) for cap-vs-spent answers.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.schemas.expense import ExpenseCreate
from app.services.expense_service import ExpenseService
from app.tools._base import dump, session_scope


@tool
def add_expense(
    trip_id: str,
    category: str,
    amount: float,
    currency: str,
    description: str | None = None,
) -> dict:
    """Record a trip expense. category: food|transport|accommodation|activities|
    shopping|entertainment|health|other. amount is in the given ISO currency."""
    with session_scope() as s:
        try:
            request = ExpenseCreate(
                category=category,
                amount=amount,
                currency=currency,
                description=description,
            )
            return dump(ExpenseService(s).create(trip_id, request))
        except AppError as e:
            raise ToolException(str(e)) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


@tool
def list_expenses(trip_id: str) -> list:
    """List all recorded expenses for a trip."""
    with session_scope() as s:
        try:
            return dump(ExpenseService(s).list(trip_id))
        except AppError as e:
            raise ToolException(str(e)) from e


@tool
def expense_summary(trip_id: str) -> dict:
    """Get the trip's expense rollup (totals by category, in USD)."""
    with session_scope() as s:
        try:
            return dump(ExpenseService(s).summary(trip_id))
        except AppError as e:
            raise ToolException(str(e)) from e


EXPENSE_TOOLS = [add_expense, list_expenses, expense_summary]
