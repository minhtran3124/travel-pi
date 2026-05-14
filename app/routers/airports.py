"""Airport endpoints."""

from fastapi import APIRouter

from app.schemas.airport import AirportListResponse
from app.schemas.pagination import PaginationDep
from app.services import airport_service

router = APIRouter(prefix="/airports", tags=["airports"])


@router.get(
    "",
    response_model=AirportListResponse,
    summary="List all supported airports (paginated)",
)
def list_airports(pagination: PaginationDep) -> AirportListResponse:
    """Return supported airports with pagination.

    ``total`` is the full count; use ``limit`` and ``offset`` to page.
    """
    page, total = pagination.page_of(airport_service.list_airports())
    return AirportListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )
