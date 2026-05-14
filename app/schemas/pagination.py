"""Shared pagination dependency, base response model, and helpers."""

from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query

from app.schemas.base import AppBaseModel

T = TypeVar("T")


class PagedResponse(AppBaseModel, Generic[T]):
    """Generic paginated response envelope shared by all list endpoints."""

    total: int
    limit: int
    offset: int
    results: list[T]


class PaginationParams:
    """Reusable FastAPI dependency for limit/offset pagination."""

    def __init__(
        self,
        limit: Annotated[
            int,
            Query(ge=1, le=500, description="Page size (1-500, default 20)"),
        ] = 20,
        offset: Annotated[
            int,
            Query(ge=0, description="Number of items to skip (default 0)"),
        ] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset

    def page_of(self, items: list) -> tuple[list, int]:
        """Return (page_slice, total_count) for the given flat list."""
        return items[self.offset : self.offset + self.limit], len(items)


PaginationDep = Annotated[PaginationParams, Depends(PaginationParams)]
