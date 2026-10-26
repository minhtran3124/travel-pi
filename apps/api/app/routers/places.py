"""Places / attractions endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.params import parse_optional_number
from app.enums import PlaceCategory, PlaceSort
from app.exceptions import NotFoundError
from app.routers.tags import Tags
from app.schemas.error import error_responses
from app.schemas.pagination import PaginationDep
from app.schemas.place import (
    Place,
    PlaceCategoryInfo,
    PlaceListResponse,
    PlaceNearbyResponse,
    PlaceNLSearchRequest,
    PlaceNLSearchResponse,
    PlaceSearchResponse,
)
from app.schemas.route import RouteResponse
from app.schemas.saved_place import (
    SavedPlace,
    SavedPlaceCreate,
    SavedPlaceFlag,
    SavedPlaceListResponse,
)
from app.services.place_service import PlaceService, get_place_service
from app.services.routing_service import RoutingService, get_routing_service
from app.services.saved_place_service import SavedPlaceDep

router = APIRouter(prefix="/places", tags=[Tags.places])

PlaceDep = Annotated[PlaceService, Depends(get_place_service)]
RoutingDep = Annotated[RoutingService, Depends(get_routing_service)]

# Retained for the dashboard's lenient HTML path; the JSON API validates via the enums.
VALID_CATEGORIES = {c.value for c in PlaceCategory}
VALID_SORTS = {s.value for s in PlaceSort}


@router.get(
    "",
    response_model=PlaceListResponse,
    summary="List all places (paginated)",
    responses=error_responses(422),
)
def list_places(
    places: PlaceDep,
    pagination: PaginationDep,
    city: Annotated[
        str | None,
        Query(description="Only places in this city — fuzzy (typo/case tolerant)"),
    ] = None,
) -> PlaceListResponse:
    """Return seeded places with pagination, optionally narrowed to a city."""
    found = places.search_places(city=city) if city else places.list_places()
    page, total = pagination.page_of(found)
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
    places: PlaceDep,
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
    """Search places with optional filters and pagination."""
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

    all_results = places.search_places(
        city=city,
        category=category.value if category else None,
        min_rating=min_rating_val,
        price_level=price_level_val,
        recommended_only=recommended,
        sort=sort.value,
    )
    page, total = pagination.page_of(all_results)
    # Echo the canonical city name when the fuzzy lookup resolved it.
    echoed_city = (places.resolve_city(city) or city) if city else None
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
    places: PlaceDep,
    pagination: PaginationDep,
) -> PlaceNLSearchResponse:
    """Parse a free-text query into structured filters, then search."""
    parsed = places.parse_nl_query(body.query)
    all_results = places.search_places(
        city=parsed.city,
        category=parsed.category,
        min_rating=parsed.min_rating,
        price_level_max=parsed.price_level,
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
def list_place_cities(places: PlaceDep) -> list[str]:
    """Return the sorted list of city names that have at least one place."""
    return places.cities()


@router.get(
    "/categories",
    response_model=list[PlaceCategoryInfo],
    summary="List all place categories",
)
def list_categories(places: PlaceDep) -> list[PlaceCategoryInfo]:
    """Return the available place categories, each with a color + icon."""
    return places.categories()


# Saved places (mutable POI overlay). Declared before "/{place_id}" so GET /places/saved is not matched as place_id="saved".

_SAVED_ID = Annotated[
    str,
    Path(description="Saved-place UUID or SPL- short code", examples=["SPL-AB23XY"]),
]


@router.post(
    "/saved",
    response_model=SavedPlace,
    status_code=status.HTTP_201_CREATED,
    summary="Create a saved place (POI overlay)",
    responses=error_responses(409, 422),
)
def create_saved_place(body: SavedPlaceCreate, service: SavedPlaceDep) -> SavedPlace:
    """Create a user/agent-saved POI; a near-duplicate (same name, within ~50 m or same city) returns 409."""
    return service.create(body)


@router.get(
    "/saved",
    response_model=SavedPlaceListResponse,
    summary="List saved places (paginated, filterable)",
    responses=error_responses(422),
)
def list_saved_places(
    pagination: PaginationDep,
    service: SavedPlaceDep,
    city: Annotated[str | None, Query(description="Exact city filter.")] = None,
    category: Annotated[str | None, Query(description="Exact category filter.")] = None,
    favorite: Annotated[
        bool | None, Query(description="Filter by favorite flag.")
    ] = None,
    visited: Annotated[
        bool | None, Query(description="Filter by visited flag.")
    ] = None,
) -> SavedPlaceListResponse:
    """Return saved places, newest first, with optional filters and pagination."""
    page, total = pagination.page_of(
        service.list(city=city, category=category, favorite=favorite, visited=visited)
    )
    return SavedPlaceListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )


@router.get(
    "/saved/{saved_id}",
    response_model=SavedPlace,
    summary="Get a saved place by ID or SPL- code",
    responses=error_responses(404),
)
def get_saved_place(saved_id: _SAVED_ID, service: SavedPlaceDep) -> SavedPlace:
    """Return one saved place (UUID or SPL- code); 404 if missing/soft-deleted."""
    return service.get(saved_id)


@router.delete(
    "/saved/{saved_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a saved place",
    responses=error_responses(404),
)
def delete_saved_place(saved_id: _SAVED_ID, service: SavedPlaceDep) -> None:
    """Soft-delete a saved place (404 if missing/already-deleted)."""
    service.delete(saved_id)


@router.post(
    "/saved/{saved_id}/favorite",
    response_model=SavedPlace,
    summary="Set the favorite flag (idempotent)",
    responses=error_responses(404, 422),
)
def set_saved_place_favorite(
    saved_id: _SAVED_ID, body: SavedPlaceFlag, service: SavedPlaceDep
) -> SavedPlace:
    """Idempotently SET the ``favorite`` flag to ``body.value``."""
    return service.set_flag(saved_id, "favorite", body.value)


@router.post(
    "/saved/{saved_id}/visited",
    response_model=SavedPlace,
    summary="Set the visited flag (idempotent)",
    responses=error_responses(404, 422),
)
def set_saved_place_visited(
    saved_id: _SAVED_ID, body: SavedPlaceFlag, service: SavedPlaceDep
) -> SavedPlace:
    """Idempotently SET the ``visited`` flag to ``body.value``."""
    return service.set_flag(saved_id, "visited", body.value)


# Note: declare "/nearby" before "/{place_id}" so it is not captured as an ID.
@router.get(
    "/nearby",
    response_model=PlaceNearbyResponse,
    summary="Find places near another place",
    responses=error_responses(404, 422),
)
def nearby_places(
    places: PlaceDep,
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
    """Return places within ``radius_km`` of ``place_id``, nearest-first (straight-line haversine)."""
    origin, results = places.nearby_places(
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
    routing: RoutingDep,
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
    """Distance and duration per travel mode (walk/bike/car) between two places, plus the recommended mode."""
    return await routing.get_place_route(origin, destination)


@router.get(
    "/{place_id}",
    response_model=Place,
    summary="Get a single place by ID",
    responses=error_responses(404, 422),
)
def get_place(
    places: PlaceDep,
    place_id: Annotated[
        str,
        Path(
            description="Place UUID from /places or /places/search",
            examples=["56f5b6d7-f0e2-5867-a9dd-087a98cff34c"],
        ),
    ],
) -> Place:
    """Return a single place, or 404 if the ID does not exist."""
    place = places.get_place(place_id)
    if place is None:
        raise NotFoundError(
            f"Place {place_id!r} not found",
            hint=(
                "Use GET /places/search?city=<city> or GET /places to find "
                "a valid place_id, or pass the short PLC-XXXX code."
            ),
        )
    return place
