"""Cities endpoint: list all known cities."""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.core.config import get_settings
from app.core.text import best_match, fuzzy_filter
from app.crud.city import CityRepository
from app.db.engine import get_session_factory
from app.exceptions import NotFoundError
from app.schemas.city import City, CityListResponse
from app.schemas.error import error_responses
from app.schemas.pagination import PaginationDep
from app.schemas.route import RouteResponse
from app.services import routing_service

router = APIRouter(prefix="/cities", tags=["cities"])

# City data is DB-backed. ``list_with_counts()`` reproduces the old
# ``_ALL_CITIES`` build (City incl. hotel_count, in seed order); ``get`` is the
# case-insensitive exact-name lookup. The repo is built from the configured DB
# at import time; it is NOT a FastAPI dependency, so tests repoint it via
# ``set_city_repo`` after seeding the temp DB (see tests/conftest.py).
_city_repo = CityRepository(get_session_factory(get_settings().database_url))


def set_city_repo(repo: CityRepository) -> None:
    """Point city reads at a different store — used by tests to read the seeded
    temporary database instead of the real travel.db."""
    global _city_repo
    _city_repo = repo


def _distinct_countries() -> list[str]:
    """Distinct country names over the seeded cities — the fuzzy-resolution
    target for the ``?country=`` filter (mirrors ``sorted({c.country ...})``)."""
    return sorted({c.country for c in _city_repo.list_with_counts()})


@router.get(
    "",
    response_model=CityListResponse,
    summary="List all cities (paginated)",
    responses=error_responses(422),
)
def list_cities(
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
    """
    results: list[City] = _city_repo.list_with_counts()
    if country:
        # Fuzzy-resolve the country name; an unrecognised one matches nothing.
        resolved_country = best_match(country, _distinct_countries(), [lambda c: c])
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
    responses=error_responses(404, 422, 502),
)
async def route_between_cities(
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
    """
    return await routing_service.get_city_route(origin, destination)


@router.get(
    "/{city_name}",
    response_model=City,
    summary="Get a single city by name",
    responses=error_responses(404, 422),
)
def get_city(
    city_name: Annotated[
        str,
        Path(description="City name (case-insensitive)", examples=["Da Nang"]),
    ],
) -> City:
    """Return a single city record, or 404 if unknown.

    ``city_name`` is matched case-insensitively (it is still an exact-name
    lookup — for typo-tolerant search use ``GET /cities?q=``).
    """
    city = _city_repo.get(city_name)
    if city is None:
        raise NotFoundError(
            f"City '{city_name}' not found",
            hint=(
                "This endpoint requires an exact name match. For "
                "typo-tolerant lookup use GET /cities?q=<partial-name>."
            ),
        )
    return city
