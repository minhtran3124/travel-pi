"""Trip expense ledger endpoints — /trips/{trip_id}/expenses."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.enums import ExpenseCategory
from app.routers.tags import Tags
from app.schemas.error import error_responses
from app.schemas.expense import (
    Expense,
    ExpenseCreate,
    ExpenseListResponse,
    ExpenseSummary,
    ExpenseUpdate,
)
from app.schemas.pagination import PaginationDep
from app.services.expense_service import ExpenseDep

router = APIRouter(
    prefix="/trips/{trip_id}/expenses",
    tags=[Tags.expenses],
    responses=error_responses(422),
)

_TRIP_ID = Annotated[str, Path(description="Trip UUID")]
_EXPENSE_ID = Annotated[str, Path(description="Expense UUID")]


@router.post(
    "",
    response_model=Expense,
    status_code=status.HTTP_201_CREATED,
    summary="Record an expense on a trip",
    responses=error_responses(404, 422),
)
def create_expense(
    trip_id: _TRIP_ID,
    body: ExpenseCreate,
    service: ExpenseDep,
) -> Expense:
    return service.create(trip_id, body)


@router.get(
    "",
    response_model=ExpenseListResponse,
    summary="List expenses for a trip",
    responses=error_responses(404, 422),
)
def list_expenses(
    trip_id: _TRIP_ID,
    service: ExpenseDep,
    pagination: PaginationDep,
    category: Annotated[
        ExpenseCategory | None, Query(description="Filter by category")
    ] = None,
    currency: Annotated[
        str | None, Query(description="Filter by ISO 4217 currency code")
    ] = None,
    date_from: Annotated[
        str | None, Query(description="Filter occurred_at >= date (ISO-8601)")
    ] = None,
    date_to: Annotated[
        str | None, Query(description="Filter occurred_at <= date (ISO-8601)")
    ] = None,
) -> ExpenseListResponse:
    expenses = service.list(
        trip_id,
        category=category.value if category else None,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
    )
    page, total = pagination.page_of(expenses)
    return ExpenseListResponse(
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        results=page,
    )


@router.get(
    "/summary",
    response_model=ExpenseSummary,
    summary="Expense summary with budget actuals for a trip",
    responses=error_responses(404),
)
def get_expense_summary(
    trip_id: _TRIP_ID,
    service: ExpenseDep,
) -> ExpenseSummary:
    return service.summary(trip_id)


@router.get(
    "/{expense_id}",
    response_model=Expense,
    summary="Get a single expense",
    responses=error_responses(404),
)
def get_expense(
    trip_id: _TRIP_ID,
    expense_id: _EXPENSE_ID,
    service: ExpenseDep,
) -> Expense:
    return service.get(trip_id, expense_id)


@router.patch(
    "/{expense_id}",
    response_model=Expense,
    summary="Update an expense",
    responses=error_responses(404, 422),
)
def update_expense(
    trip_id: _TRIP_ID,
    expense_id: _EXPENSE_ID,
    body: ExpenseUpdate,
    service: ExpenseDep,
) -> Expense:
    return service.update(trip_id, expense_id, body)


@router.delete(
    "/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an expense (soft delete)",
    responses=error_responses(404),
)
def delete_expense(
    trip_id: _TRIP_ID,
    expense_id: _EXPENSE_ID,
    service: ExpenseDep,
) -> None:
    service.delete(trip_id, expense_id)
