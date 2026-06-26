"""Expense ledger schemas — on-trip spend tracking."""

from pydantic import Field, computed_field, field_validator

from app.core.codes import prefixed_code
from app.enums import ExpenseCategory
from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse

EXPENSE_CODE_PREFIX = "EXP"


class ExpenseCreate(AppBaseModel):
    category: ExpenseCategory
    amount: float = Field(gt=0, description="Spend amount in the original currency.")
    currency: str = Field(description="ISO 4217 currency code, e.g. 'USD'.")
    description: str | None = None
    occurred_at: str | None = Field(
        default=None,
        description="ISO-8601 datetime of spend. None = service sets to now.",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalise_currency(cls, v: str) -> str:
        return v.strip().upper()


class ExpenseUpdate(AppBaseModel):
    category: ExpenseCategory | None = None
    amount: float | None = Field(default=None, gt=0)
    currency: str | None = None
    description: str | None = None
    occurred_at: str | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def normalise_currency(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return v.strip().upper()


class Expense(ExpenseCreate):
    id: str
    trip_id: str
    amount_usd: float
    fx_rate: float
    created_at: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def short_code(self) -> str:
        """Friendly ``EXP-XXXXXX`` reference code derived from the expense ID."""
        return prefixed_code(EXPENSE_CODE_PREFIX, self.id)


class ExpenseListResponse(PagedResponse[Expense]):
    """Response body for ``GET /trips/{id}/expenses``."""


class CategoryExpense(AppBaseModel):
    """Rolled-up spend for one expense category."""

    category: ExpenseCategory
    total_usd: float
    count: int


class CurrencyExpense(AppBaseModel):
    """Rolled-up spend for one currency."""

    currency: str
    total_original: float
    total_usd: float
    count: int


class ExpenseBudgetActuals(AppBaseModel):
    """Comparison of trip budget cap vs. actual spend."""

    total_cap: float | None
    booked_spent: float
    expense_spent: float
    total_spent: float
    total_remaining: float | None
    over_budget: bool


class ExpenseSummary(AppBaseModel):
    """Aggregated expense summary for a trip."""

    expense_count: int
    total_usd: float
    by_category: list[CategoryExpense]
    by_currency: list[CurrencyExpense]
    budget: ExpenseBudgetActuals
