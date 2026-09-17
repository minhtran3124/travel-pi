import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, get_current_user
from app.db.session import get_session
from app.exceptions import NotFoundError
from app.repositories.expense import ExpenseRepository
from app.repositories.fx import FxRepository
from app.repositories.trip import TripRepository
from app.schemas.expense import (
    CategoryExpense,
    CurrencyExpense,
    Expense,
    ExpenseBudgetActuals,
    ExpenseCreate,
    ExpenseSummary,
    ExpenseUpdate,
)


def _money(value: float, places: int = 2) -> float:
    quant = Decimal(10) ** -places
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


class ExpenseService:
    def __init__(self, session: Session, user_id: str) -> None:
        """Bind the store to one owner."""
        self._repo = ExpenseRepository(session)
        self._trip_repo = TripRepository(session)
        self._fx = FxRepository(session)
        self._session = session
        self._user_id = user_id

    def _validate_trip(self, trip_id: str) -> None:
        """Missing or not-owned both raise ``NotFoundError`` so the route can't confirm a guessed id."""
        trip = self._trip_repo.get_trip(trip_id, self._user_id)
        if trip is None:
            raise NotFoundError(f"Trip {trip_id!r} not found.")

    def _resolve_currency(self, currency: str) -> str:
        normalised = currency.strip().upper()
        rate = self._fx.rate(normalised)
        if rate is None:
            valid = ", ".join(self._fx.valid_codes())
            raise NotFoundError(
                f"Unknown currency {normalised!r}. Supported codes: {valid}."
            )
        return normalised

    def _to_usd(self, amount: float, currency: str) -> tuple[float, float]:
        fx_rate = self._fx.rate("USD") / self._fx.rate(currency)
        amount_usd = _money(amount * fx_rate)
        return amount_usd, fx_rate

    def create(self, trip_id: str, request: ExpenseCreate) -> Expense:
        self._validate_trip(trip_id)
        currency = self._resolve_currency(request.currency)
        amount_usd, fx_rate = self._to_usd(request.amount, currency)
        occurred_at = request.occurred_at or datetime.now(timezone.utc).isoformat()
        expense = Expense(
            id=str(uuid.uuid4()),
            trip_id=trip_id,
            category=request.category,
            amount=request.amount,
            currency=currency,
            amount_usd=amount_usd,
            fx_rate=fx_rate,
            description=request.description,
            occurred_at=occurred_at,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return self._repo.add(expense)

    def get(self, trip_id: str, expense_id: str) -> Expense:
        self._validate_trip(trip_id)
        expense = self._repo.get(expense_id)
        if expense is None or expense.trip_id != trip_id:
            raise NotFoundError(
                f"Expense {expense_id!r} not found on trip {trip_id!r}."
            )
        return expense

    def list(self, trip_id: str, **filters) -> list[Expense]:
        self._validate_trip(trip_id)
        return self._repo.list(trip_id, **filters)

    def update(self, trip_id: str, expense_id: str, request: ExpenseUpdate) -> Expense:
        expense = self.get(trip_id, expense_id)
        fields = request.model_dump(exclude_none=True)
        new_amount = fields.get("amount", expense.amount)
        new_currency_raw = fields.get("currency", expense.currency)
        new_currency = self._resolve_currency(new_currency_raw)
        if "currency" in fields or "amount" in fields:
            amount_usd, fx_rate = self._to_usd(new_amount, new_currency)
            fields["amount_usd"] = amount_usd
            fields["fx_rate"] = fx_rate
        if "currency" in fields:
            fields["currency"] = new_currency
        updated = self._repo.update(expense_id, **fields)
        if updated is None:
            raise NotFoundError(f"Expense {expense_id!r} not found.")
        return updated

    def delete(self, trip_id: str, expense_id: str) -> None:
        self.get(trip_id, expense_id)
        self._repo.soft_delete(expense_id, when=datetime.now(timezone.utc).isoformat())

    def summary(self, trip_id: str) -> ExpenseSummary:
        self._validate_trip(trip_id)
        expenses = self._repo.list(trip_id)

        total_usd = _money(sum(e.amount_usd for e in expenses))

        cat_map: dict[str, dict] = {}
        for e in expenses:
            key = e.category
            if key not in cat_map:
                cat_map[key] = {"total_usd": 0.0, "count": 0}
            cat_map[key]["total_usd"] = _money(cat_map[key]["total_usd"] + e.amount_usd)
            cat_map[key]["count"] += 1
        by_category = [
            CategoryExpense(category=k, total_usd=v["total_usd"], count=v["count"])
            for k, v in cat_map.items()
        ]

        curr_map: dict[str, dict] = {}
        for e in expenses:
            key = e.currency
            if key not in curr_map:
                curr_map[key] = {"total_original": 0.0, "total_usd": 0.0, "count": 0}
            curr_map[key]["total_original"] = _money(
                curr_map[key]["total_original"] + e.amount
            )
            curr_map[key]["total_usd"] = _money(
                curr_map[key]["total_usd"] + e.amount_usd
            )
            curr_map[key]["count"] += 1
        by_currency = [
            CurrencyExpense(
                currency=k,
                total_original=v["total_original"],
                total_usd=v["total_usd"],
                count=v["count"],
            )
            for k, v in curr_map.items()
        ]

        from app.services.trip_service import TripService

        trip_budget = TripService(self._session, self._user_id).get_trip_budget(trip_id)
        booked_spent = _money(trip_budget.total_spent)
        expense_spent = total_usd
        total_spent = _money(booked_spent + expense_spent)
        total_cap = trip_budget.total_cap
        total_remaining = (
            _money(total_cap - total_spent) if total_cap is not None else None
        )
        over_budget = total_cap is not None and total_spent > total_cap

        budget_actuals = ExpenseBudgetActuals(
            total_cap=total_cap,
            booked_spent=booked_spent,
            expense_spent=expense_spent,
            total_spent=total_spent,
            total_remaining=total_remaining,
            over_budget=over_budget,
        )

        return ExpenseSummary(
            expense_count=len(expenses),
            total_usd=total_usd,
            by_category=by_category,
            by_currency=by_currency,
            budget=budget_actuals,
        )


def get_expense_service(
    session: Annotated[Session, Depends(get_session)],
    auth_user: Annotated[AuthUser, Depends(get_current_user)],
) -> ExpenseService:
    """FastAPI dependency: an expense store bound to the session and caller."""
    return ExpenseService(session, auth_user.id)


ExpenseDep = Annotated[ExpenseService, Depends(get_expense_service)]
