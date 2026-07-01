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
    """FastAPI dependency: a city repository bound to the request session.

    ``list_with_counts()`` reproduces the old ``_ALL_CITIES`` build (City incl.
    hotel_count, in seed order); ``get`` is the case-insensitive exact-name
    lookup.

    :param session: The request-scoped DB session.
    :return: A city repository bound to ``session``.
    """
    return CityRepository(session)


CityRepoDep = Annotated[CityRepository, Depends(get_city_repo)]
RoutingDep = Annotated[RoutingService, Depends(get_routing_service)]


def _distinct_countries(city_repo: CityRepository) -> list[str]:
    """Distinct country names over the seeded cities — the fuzzy-resolution
    target for the ``?country=`` filter (mirrors ``sorted({c.country ...})``).

    :param city_repo: The city repository.
    :return: The sorted distinct country names.
    """
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
    """Return known cities with pagination.

    Each entry includes the city name, country, IATA airport codes, and hotel
    count. ``total`` reflects the full match count before pagination. When
    ``q`` is given, results are fuzzy-matched and ranked by relevance instead
    of left in seed order.

    :param city_repo: The city repository.
    :param pagination: The pagination params (limit/offset).
    :param q: Optional fuzzy search on city name / country.
    :param country: Optional fuzzy filter by country name.
    :param has_hotels: Optional filter for whether the city has hotel data.
    :return: The matching cities, paginated.
    """
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


# Note: declare "/route" before "/{city_name}" so it is not captured as a name.
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
    """Return distance and duration per travel mode (walk / bike / car)
    between two cities, plus the recommended mode for the distance.

    City names are matched case-insensitively. Uses OpenRouteService for real
    road routing when ``ORS_API_KEY`` is configured; otherwise falls back to
    an offline straight-line estimate (see the ``source`` field). Returns 404
    if either city name is unknown, and 502 if a configured routing provider
    is unreachable.

    :param routing: The routing service.
    :param origin: City name to start from.
    :param destination: City name to travel to.
    :return: Distance/duration per travel mode plus the recommended mode.
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
    """Return a single city record, or 404 if unknown.

    ``city_name`` is matched case-insensitively (it is still an exact-name
    lookup — for typo-tolerant search use ``GET /cities?q=``).

    :param city_repo: The city repository.
    :param city_name: City name (case-insensitive).
    :return: The matching city.
    """
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
