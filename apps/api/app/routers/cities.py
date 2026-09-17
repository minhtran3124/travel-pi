"""Cities endpoint: list all known cities."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.text import best_match, fuzzy_filter
from app.db.session import get_session
from app.exceptions import NotFoundError
from app.repositories.city import CityRepository
from app.routers.tags import Tags
from app.schemas.city import City, CityListResponse
from app.schemas.error import error_responses
from app.schemas.pagination import PaginationDep
from app.schemas.route import RouteResponse
from app.services.routing_service import RoutingService, get_routing_service

router = APIRouter(prefix="/cities", tags=[Tags.cities], responses=error_responses(422))


def get_city_repo(
    session: Annotated[Session, Depends(get_session)],
) -> CityRepository:
    """City repository bound to the request session."""
    return CityRepository(session)


CityRepoDep = Annotated[CityRepository, Depends(get_city_repo)]
RoutingDep = Annotated[RoutingService, Depends(get_routing_service)]


def _distinct_countries(city_repo: CityRepository) -> list[str]:
    """Distinct country names — the fuzzy-resolution target for the ``?country=`` filter."""
    return sorted({c.country for c in city_repo.list_with_counts()})


@router.get(
    "",
    response_model=CityListResponse,
    summary="List all cities (paginated)",
)
def list_cities(
    city_repo: CityRepoDep,
    pagination: PaginationDep,
    q: str | None = Query(
        None,
        description=(
            "Free-text fuzzy search on city name / country — tolerant of "
            "typos and partial input (e.g. 'danang', 'phu ket'). Results are "
            "ranked best-match-first."
        ),
        examples=["danang"],
    ),
    country: str | None = Query(
        None,
        description="Filter by country name (fuzzy — typo/case tolerant)",
        examples=["Vietnam"],
    ),
    has_hotels: bool | None = Query(
        None,
        description="If true, return only cities with hotel data",
        examples=[True],
    ),
) -> CityListResponse:
    """Return known cities with pagination; ``q`` fuzzy-ranks by relevance."""
    results: list[City] = city_repo.list_with_counts()
    if country:
        # Fuzzy-resolve the country name; an unrecognised one matches nothing.
        resolved_country = best_match(
            country, _distinct_countries(city_repo), [lambda c: c]
        )
        results = (
            [c for c in results if c.country == resolved_country]
            if resolved_country
            else []
        )
    if has_hotels is True:
        results = [c for c in results if c.hotel_count > 0]
    elif has_hotels is False:
        results = [c for c in results if c.hotel_count == 0]
    if q:
        results = fuzzy_filter(q, results, [lambda c: c.name, lambda c: c.country])

    page, total = pagination.page_of(results)
    return CityListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )


# Declare "/route" before "/{city_name}" so it isn't captured as a name.
@router.get(
    "/route",
    response_model=RouteResponse,
    summary="Route between two cities — distance, time, and best travel mode",
    responses=error_responses(404, 502),
)
async def route_between_cities(
    routing: RoutingDep,
    origin: Annotated[
        str,
        Query(description="City name to start from", examples=["Da Nang"]),
    ],
    destination: Annotated[
        str,
        Query(description="City name to travel to", examples=["Hoi An"]),
    ],
) -> RouteResponse:
    """Distance/duration per travel mode plus the recommended mode between two cities.

    Uses OpenRouteService when ``ORS_API_KEY`` is set, else an offline straight-line estimate.
    """
    return await routing.get_city_route(origin, destination)


@router.get(
    "/{city_name}",
    response_model=City,
    summary="Get a single city by name",
    responses=error_responses(404),
)
def get_city(
    city_repo: CityRepoDep,
    city_name: Annotated[
        str,
        Path(description="City name (case-insensitive)", examples=["Da Nang"]),
    ],
) -> City:
    """Return a single city record (exact case-insensitive name), or 404 if unknown."""
    city = city_repo.get(city_name)
    if city is None:
        raise NotFoundError(
            f"City '{city_name}' not found",
            hint=(
                "This endpoint requires an exact name match. For "
                "typo-tolerant lookup use GET /cities?q=<partial-name>."
            ),
        )
    return city
