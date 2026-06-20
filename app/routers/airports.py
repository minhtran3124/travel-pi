"""Airport endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.text import fuzzy_filter
from app.schemas.airport import AirportListResponse
from app.schemas.error import error_responses
from app.schemas.pagination import PaginationDep
from app.services.airport_service import AirportService, get_airport_service

router = APIRouter(prefix="/airports", tags=["airports"])

AirportDep = Annotated[AirportService, Depends(get_airport_service)]


@router.get(
    "",
    response_model=AirportListResponse,
    summary="List all supported airports (paginated)",
    responses=error_responses(422),
)
def list_airports(
    airports_svc: AirportDep,
    pagination: PaginationDep,
    q: str | None = Query(
        None,
        description=(
            "Free-text fuzzy search on IATA code / airport name / city — "
            "tolerant of typos and partial input (e.g. 'danang', 'dad'). "
            "Results are ranked best-match-first."
        ),
        examples=["danang"],
    ),
) -> AirportListResponse:
    """Return supported airports with pagination.

    ``total`` is the full count; use ``limit`` and ``offset`` to page. When
    ``q`` is given, results are fuzzy-matched and ranked by relevance instead
    of left in seed order.
    """
    results = airports_svc.list_airports()
    if q:
        results = fuzzy_filter(
            q,
            results,
            [lambda a: a.code, lambda a: a.name, lambda a: a.city],
        )
    page, total = pagination.page_of(results)
    return AirportListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )
