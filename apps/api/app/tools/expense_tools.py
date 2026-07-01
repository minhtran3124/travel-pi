"""Expense / budget tools (specs/travel-agent Task 3.4).

Wrap ``ExpenseService`` for the budget sub-agent: record spend, list it, and roll
it up. Pairs with ``get_trip_budget`` (trip_tools) for cap-vs-spent answers.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool
from pydantic import Field

from app.enums import ExpenseCategory
from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.schemas.expense import ExpenseCreate
from app.services.expense_service import ExpenseService
from app.tools._base import dump, log_tool_call, session_scope


class AddExpenseArgs(AppBaseModel):
    trip_id: str = Field(..., description="The trip to record the expense against.")
    category: ExpenseCategory = Field(..., description="The expense category.")
    amount: float = Field(..., gt=0, description="The expense amount, in `currency`.")
    currency: str = Field(..., description="ISO currency code for `amount`.")
    description: str | None = Field(
        None, description="Optional free-text description of the expense."
    )


class ListExpensesArgs(AppBaseModel):
    trip_id: str = Field(..., description="The trip to list expenses for.")


class ExpenseSummaryArgs(AppBaseModel):
    trip_id: str = Field(..., description="The trip to summarise.")


@tool(args_schema=AddExpenseArgs)
def add_expense(
    trip_id: str,
    category: str,
    amount: float,
    currency: str,
    description: str | None = None,
) -> dict:
    """Record a trip expense.

    :param trip_id: The trip to record the expense against.
    :param category: The expense category.
    :param amount: The expense amount, in ``currency``.
    :param currency: ISO currency code for ``amount``.
    :param description: Optional free-text description of the expense.
    :return: The created expense record.
    """
    log_tool_call("add_expense", locals())
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


@tool(args_schema=ListExpensesArgs)
def list_expenses(trip_id: str) -> list:
    """List all recorded expenses for a trip.

    :param trip_id: The trip to list expenses for.
    :return: All recorded expenses for the trip.
    """
    log_tool_call("list_expenses", locals())
    with session_scope() as s:
        try:
            return dump(ExpenseService(s).list(trip_id))
        except AppError as e:
            raise ToolException(str(e)) from e


@tool(args_schema=ExpenseSummaryArgs)
def expense_summary(trip_id: str) -> dict:
    """Get the trip's expense rollup (totals by category, in USD).

    :param trip_id: The trip to summarise.
    :return: The trip's expense rollup, with totals by category in USD.
    """
    log_tool_call("expense_summary", locals())
    with session_scope() as s:
        try:
            return dump(ExpenseService(s).summary(trip_id))
        except AppError as e:
            raise ToolException(str(e)) from e


EXPENSE_TOOLS = [add_expense, list_expenses, expense_summary]
