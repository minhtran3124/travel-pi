"""Data-access layer for expenses; business rules live in services/expense_service.py. Soft-delete filtered from all reads."""

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo
from app.schemas.expense import Expense


def _row_to_expense(row: models.Expense) -> Expense:
    return Expense(
        id=row.id,
        trip_id=row.trip_id,
        category=row.category,
        amount=row.amount,
        currency=row.currency,
        amount_usd=row.amount_usd,
        fx_rate=row.fx_rate,
        description=row.description,
        occurred_at=row.occurred_at,
        created_at=row.created_at,
    )


class ExpenseRepository(Repo):
    """ORM-backed store of expenses rows."""

    def add(self, expense: Expense) -> Expense:
        row = models.Expense(
            id=expense.id,
            trip_id=expense.trip_id,
            category=expense.category,
            amount=expense.amount,
            currency=expense.currency,
            amount_usd=expense.amount_usd,
            fx_rate=expense.fx_rate,
            description=expense.description,
            occurred_at=expense.occurred_at,
            created_at=expense.created_at,
        )
        with self._session() as s:
            s.add(row)
            self._commit(s)
        return expense

    def get(self, id_: str) -> Expense | None:
        """Fetch a live expense by UUID (None if deleted or missing)."""
        with self._session() as s:
            row = s.scalars(
                select(models.Expense).where(
                    models.Expense.id == id_,
                    models.Expense.deleted_at.is_(None),
                )
            ).first()
            if row is not None:
                return _row_to_expense(row)
        return None

    def list(
        self,
        trip_id: str,
        *,
        category: str | None = None,
        currency: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[Expense]:
        stmt = select(models.Expense).where(
            models.Expense.trip_id == trip_id,
            models.Expense.deleted_at.is_(None),
        )
        if category is not None:
            stmt = stmt.where(models.Expense.category == category)
        if currency is not None:
            stmt = stmt.where(models.Expense.currency == currency)
        if date_from is not None:
            stmt = stmt.where(models.Expense.occurred_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(models.Expense.occurred_at <= date_to)
        stmt = stmt.order_by(models.Expense.created_at.desc(), models.Expense.id.desc())
        with self._session() as s:
            return [_row_to_expense(r) for r in s.scalars(stmt).all()]

    def update(self, id_: str, **fields) -> Expense | None:
        """Update mutable fields on a live expense row; None if no live row matches."""
        with self._session() as s:
            row = s.scalars(
                select(models.Expense).where(
                    models.Expense.id == id_,
                    models.Expense.deleted_at.is_(None),
                )
            ).first()
            if row is None:
                return None
            for field, value in fields.items():
                setattr(row, field, value)
            self._commit(s)
            return _row_to_expense(row)

    def soft_delete(self, id_: str, *, when: str) -> bool:
        """Stamp ``deleted_at`` on a live expense row (soft delete)."""
        with self._session() as s:
            row = s.scalars(
                select(models.Expense).where(
                    models.Expense.id == id_,
                    models.Expense.deleted_at.is_(None),
                )
            ).first()
            if row is None:
                return False
            row.deleted_at = when
            self._commit(s)
            return True
