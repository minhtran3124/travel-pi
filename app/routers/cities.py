"""Cities endpoint: list all known cities."""

from fastapi import APIRouter, Query

from app.data.cities import CITIES
from app.data.hotels import HOTELS
from app.exceptions import NotFoundError
from app.schemas.city import City, CityListResponse
from app.schemas.pagination import PaginationDep

router = APIRouter(prefix="/cities", tags=["cities"])

# Pre-compute hotel counts per city once at startup.
_HOTEL_COUNTS: dict[str, int] = {}
for _h in HOTELS:
    _HOTEL_COUNTS[_h["city"]] = _HOTEL_COUNTS.get(_h["city"], 0) + 1

# Build the full city list once.
_ALL_CITIES: list[City] = [
    City(
        name=c["name"],
        country=c["country"],
        airport_codes=c["airport_codes"],
        hotel_count=_HOTEL_COUNTS.get(c["name"], 0),
    )
    for c in CITIES
]

# Index by name for fast single-city lookup.
_BY_NAME: dict[str, City] = {c.name: c for c in _ALL_CITIES}


@router.get(
    "",
    response_model=CityListResponse,
    summary="List all cities (paginated)",
)
def list_cities(
    pagination: PaginationDep,
    country: str | None = Query(None, description="Filter by country name"),
    has_hotels: bool | None = Query(
        None, description="If true, return only cities with hotel data"
    ),
) -> CityListResponse:
    """Return known cities with pagination.

    Each entry includes the city name, country, IATA airport codes, and hotel
    count. ``total`` reflects the full match count before pagination.
    """
    results: list[City] = list(_ALL_CITIES)
    if country:
        target = country.strip().lower()
        results = [c for c in results if c.country.lower() == target]
    if has_hotels is True:
        results = [c for c in results if c.hotel_count > 0]
    elif has_hotels is False:
        results = [c for c in results if c.hotel_count == 0]

    page, total = pagination.page_of(results)
    return CityListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )


@router.get(
    "/{city_name}",
    response_model=City,
    summary="Get a single city by name",
)
def get_city(city_name: str) -> City:
    """Return a single city record, or 404 if unknown."""
    city = _BY_NAME.get(city_name)
    if city is None:
        raise NotFoundError(f"City '{city_name}' not found")
    return city
