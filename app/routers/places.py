"""Places / attractions endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.core.params import parse_optional_number
from app.enums import PlaceCategory, PlaceSort
from app.exceptions import NotFoundError
from app.schemas.error import error_responses
from app.schemas.pagination import PaginationDep
from app.schemas.place import (
    Place,
    PlaceListResponse,
    PlaceNearbyResponse,
    PlaceNLSearchRequest,
    PlaceNLSearchResponse,
    PlaceSearchResponse,
)
from app.schemas.route import RouteResponse
from app.services import place_service, routing_service

router = APIRouter(prefix="/places", tags=["places"])

# Valid sets retained for the dashboard's lenient HTML path; the JSON API
# now relies on the ``PlaceCategory`` / ``PlaceSort`` enums for validation.
VALID_CATEGORIES = {c.value for c in PlaceCategory}
VALID_SORTS = {s.value for s in PlaceSort}


@router.get(
    "",
    response_model=PlaceListResponse,
    summary="List all places (paginated)",
    responses=error_responses(422),
)
def list_places(pagination: PaginationDep) -> PlaceListResponse:
    """Return all seeded places with pagination.

    ``total`` is the full count; use ``limit`` and ``offset`` to page.
    """
    page, total = pagination.page_of(place_service.list_places())
    return PlaceListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )


@router.get(
    "/search",
    response_model=PlaceSearchResponse,
    summary="Search places by city and optional filters",
    responses=error_responses(422),
)
def search_places(
    pagination: PaginationDep,
    city: Annotated[
        str | None,
        Query(
            description="City name — fuzzy (typo/case tolerant)",
            examples=["Da Nang"],
        ),
    ] = None,
    category: Annotated[
        PlaceCategory | None,
        Query(
            description="Category filter — Swagger renders the dropdown.",
            examples=["restaurant"],
        ),
    ] = None,
    min_rating: Annotated[
        str | None,
        Query(
            description="Minimum rating (0–5); empty string treated as no filter",
            examples=["4"],
        ),
    ] = None,
    price_level: Annotated[
        str | None,
        Query(
            description="Exact price level 1–4 (1=free/cheap … 4=luxury); empty string treated as no filter",
            examples=["2"],
        ),
    ] = None,
    recommended: Annotated[
        bool,
        Query(description="Return only editor-recommended places", examples=[True]),
    ] = False,
    sort: Annotated[
        PlaceSort,
        Query(
            description="Sort order — Swagger renders the dropdown.",
            examples=["rating_desc"],
        ),
    ] = PlaceSort.RATING_DESC,
) -> PlaceSearchResponse:
    """Search places with optional filters and pagination.

    Unknown cities return ``total: 0`` (not a 404). ``min_rating`` and
    ``price_level`` accept empty strings as "no filter".
    ``total`` reflects the full match count; ``results`` is the current page.
    """
    min_rating_val, err = parse_optional_number(
        min_rating, label="min_rating", kind=float, minimum=0, maximum=5
    )
    if err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err)
    price_level_val, err = parse_optional_number(
        price_level, label="price_level", kind=int, minimum=1, maximum=4
    )
    if err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err)

    all_results = place_service.search_places(
        city=city,
        category=category.value if category else None,
        min_rating=min_rating_val,
        price_level=price_level_val,
        recommended_only=recommended,
        sort=sort.value,
    )
    page, total = pagination.page_of(all_results)
    # Echo the canonical city name when the fuzzy lookup resolved it.
    echoed_city = (place_service.resolve_city(city) or city) if city else None
    return PlaceSearchResponse(
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        city=echoed_city,
        category=category.value if category else None,
        min_rating=min_rating_val,
        price_level=price_level_val,
        recommended_only=recommended,
        sort=sort.value,
        results=page,
    )


@router.post(
    "/search/nl",
    response_model=PlaceNLSearchResponse,
    summary="Natural-language place search",
    responses=error_responses(422),
)
def search_places_nl(
    body: PlaceNLSearchRequest,
    pagination: PaginationDep,
) -> PlaceNLSearchResponse:
    """Parse a free-text query into structured filters, then search.

    The parsed filters are echoed back in ``parsed`` so the caller can see
    how the query was interpreted. Budget phrases ('under $40') and price
    adjectives ('cheap') map to a single ``price_level`` band, matched
    exactly; unrecognised words are ignored. Pagination uses the standard
    ``limit`` / ``offset`` query params.
    """
    parsed = place_service.parse_nl_query(body.query)
    all_results = place_service.search_places(
        city=parsed.city,
        category=parsed.category,
        min_rating=parsed.min_rating,
        price_level=parsed.price_level,
    )
    page, total = pagination.page_of(all_results)
    return PlaceNLSearchResponse(
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        query=body.query,
        parsed=parsed,
        results=page,
    )


@router.get(
    "/cities",
    response_model=list[str],
    summary="List all cities that have places",
)
def list_cities() -> list[str]:
    """Return the sorted list of city names that have at least one place."""
    return place_service.CITIES


@router.get(
    "/categories",
    response_model=list[str],
    summary="List all place categories",
)
def list_categories() -> list[str]:
    """Return the sorted list of available place categories."""
    return place_service.CATEGORIES


# Note: declare "/nearby" before "/{place_id}" so it is not captured as an ID.
@router.get(
    "/nearby",
    response_model=PlaceNearbyResponse,
    summary="Find places near another place",
    responses=error_responses(404, 422),
)
def nearby_places(
    place_id: Annotated[
        str,
        Query(
            description="The place to search around",
            examples=["56f5b6d7-f0e2-5867-a9dd-087a98cff34c"],
        ),
    ],
    radius_km: Annotated[
        float,
        Query(
            gt=0, le=50, description="Search radius in kilometres (0–50)", examples=[5]
        ),
    ] = 5.0,
    limit: Annotated[
        int,
        Query(ge=1, le=50, description="Maximum number of results", examples=[10]),
    ] = 10,
    category: Annotated[
        PlaceCategory | None,
        Query(
            description="Optional category filter — Swagger renders the dropdown.",
            examples=["restaurant"],
        ),
    ] = None,
) -> PlaceNearbyResponse:
    """Return places within ``radius_km`` of ``place_id``, nearest-first.

    Distances are straight-line (haversine) — no external call. The origin
    place itself is excluded. Returns 404 if ``place_id`` is unknown or has
    no coordinates; an empty ``results`` list (not a 404) when nothing is in
    range.
    """
    origin, results = place_service.nearby_places(
        place_id,
        radius_km=radius_km,
        limit=limit,
        category=category.value if category else None,
    )
    return PlaceNearbyResponse(
        origin_place_id=origin.id,
        radius_km=radius_km,
        count=len(results),
        results=results,
    )


# Note: declare "/route" before "/{place_id}" so it is not captured as an ID.
@router.get(
    "/route",
    response_model=RouteResponse,
    summary="Route between two places — distance, time, and best travel mode",
    responses=error_responses(404, 422, 502),
)
async def route_between_places(
    origin: Annotated[
        str,
        Query(
            description="Place ID to start from",
            examples=["56f5b6d7-f0e2-5867-a9dd-087a98cff34c"],
        ),
    ],
    destination: Annotated[
        str,
        Query(
            description="Place ID to travel to",
            examples=["26afc73a-6773-55c9-8e61-1f0fe75576e7"],
        ),
    ],
) -> RouteResponse:
    """Return distance and duration per travel mode (walk / bike / car)
    between two places, plus the recommended mode for the distance.

    Uses OpenRouteService for real road routing when ``ORS_API_KEY`` is
    configured; otherwise falls back to an offline straight-line estimate
    (see the ``source`` field). Returns 404 if either place ID is unknown or
    has no coordinates, and 502 if a configured routing provider is
    unreachable.
    """
    return await routing_service.get_place_route(origin, destination)


@router.get(
    "/{place_id}",
    response_model=Place,
    summary="Get a single place by ID",
    responses=error_responses(404, 422),
)
def get_place(
    place_id: Annotated[
        str,
        Path(
            description="Place UUID from /places or /places/search",
            examples=["56f5b6d7-f0e2-5867-a9dd-087a98cff34c"],
        ),
    ],
) -> Place:
    """Return a single place, or 404 if the ID does not exist."""
    place = place_service.get_place(place_id)
    if place is None:
        raise NotFoundError(
            f"Place {place_id!r} not found",
            hint=(
                "Use GET /places/search?city=<city> or GET /places to find "
                "a valid place_id, or pass the short PLC-XXXX code."
            ),
        )
    return place
