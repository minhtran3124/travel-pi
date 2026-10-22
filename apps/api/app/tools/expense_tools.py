"""Expense / budget tools wrapping ``ExpenseService`` for the budget sub-agent."""

from __future__ import annotations

from typing import Annotated

from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from app.enums import ExpenseCategory
from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.schemas.expense import ExpenseCreate
from app.services.expense_service import ExpenseService
from app.tools._base import dump, log_tool_call, session_scope, tool_error


# Each schema must DECLARE the injected user_id or ToolNode never injects it; it stays hidden from the
# model. Signatures keep their Annotated metadata because MCP serves the raw signature.
class _ExpenseOwnerArgs(AppBaseModel):
    user_id: Annotated[str, InjectedState("user_id")] = Field(
        ...,
        description="The trip's owner. Injected from graph state (#118).",
    )


class AddExpenseArgs(_ExpenseOwnerArgs):
    trip_id: str = Field(..., description="The trip to record the expense against.")
    category: ExpenseCategory = Field(..., description="The expense category.")
    amount: float = Field(..., gt=0, description="The expense amount, in `currency`.")
    currency: str = Field(..., description="ISO currency code for `amount`.")
    description: str | None = Field(None, description="Optional free-text description.")


class ListExpensesArgs(_ExpenseOwnerArgs):
    trip_id: str = Field(..., description="The trip to list expenses for.")


class ExpenseSummaryArgs(_ExpenseOwnerArgs):
    trip_id: str = Field(..., description="The trip to summarise.")


@tool(args_schema=AddExpenseArgs)
def add_expense(
    trip_id: Annotated[
        str, Field(description="The trip to record the expense against.")
    ],
    user_id: Annotated[
        str,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ],
    category: Annotated[ExpenseCategory, Field(description="The expense category.")],
    amount: Annotated[
        float, Field(gt=0, description="The expense amount, in `currency`.")
    ],
    currency: Annotated[str, Field(description="ISO currency code for `amount`.")],
    description: Annotated[
        str | None, Field(description="Optional free-text description.")
    ] = None,
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
            return dump(ExpenseService(s, user_id).create(trip_id, request))
        except AppError as e:
            raise tool_error(e) from e
        except ValueError as e:
            raise ToolException(str(e)) from e


@tool(args_schema=ListExpensesArgs)
def list_expenses(
    trip_id: Annotated[str, Field(description="The trip to list expenses for.")],
    user_id: Annotated[
        str,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ],
) -> list:
    """List all recorded expenses for a trip.

    :param trip_id: The trip to list expenses for.
    :return: All recorded expenses for the trip.
    """
    log_tool_call("list_expenses", locals())
    with session_scope() as s:
        try:
            return dump(ExpenseService(s, user_id).list(trip_id))
        except AppError as e:
            raise tool_error(e) from e


@tool(args_schema=ExpenseSummaryArgs)
def expense_summary(
    trip_id: Annotated[str, Field(description="The trip to summarise.")],
    user_id: Annotated[
        str,
        InjectedState("user_id"),
        Field(description="The trip's owner. Injected from graph state (#118)."),
    ],
) -> dict:
    """Get the trip's expense rollup (totals by category, in USD).

    :param trip_id: The trip to summarise.
    :return: The trip's expense rollup, with totals by category in USD.
    """
    log_tool_call("expense_summary", locals())
    with session_scope() as s:
        try:
            return dump(ExpenseService(s, user_id).summary(trip_id))
        except AppError as e:
            raise tool_error(e) from e


EXPENSE_TOOLS = [add_expense, list_expenses, expense_summary]
