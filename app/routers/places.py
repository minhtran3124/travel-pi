"""Places / attractions endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.exceptions import NotFoundError
from app.schemas.pagination import PaginationDep
from app.schemas.place import Place, PlaceListResponse, PlaceSearchResponse
from app.services import place_service

router = APIRouter(prefix="/places", tags=["places"])

VALID_CATEGORIES = {
    "attraction",
    "restaurant",
    "cafe",
    "activity",
    "nightlife",
    "shopping",
}
VALID_SORTS = {
    "rating_desc",
    "rating_asc",
    "name",
    "price_asc",
    "price_desc",
    "reviews_desc",
}


@router.get(
    "",
    response_model=PlaceListResponse,
    summary="List all places (paginated)",
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
)
def search_places(
    pagination: PaginationDep,
    city: Annotated[
        str | None,
        Query(
            description="City name, case-insensitive exact match", examples=["Da Nang"]
        ),
    ] = None,
    category: Annotated[
        str | None,
        Query(
            description="Category filter: attraction | restaurant | cafe | activity | nightlife | shopping",
            examples=["restaurant"],
        ),
    ] = None,
    min_rating: Annotated[
        str | None,
        Query(description="Minimum rating (0–5); empty string treated as no filter"),
    ] = None,
    price_level: Annotated[
        str | None,
        Query(
            description="Exact price level 1–4 (1=free/cheap … 4=luxury); empty string treated as no filter"
        ),
    ] = None,
    recommended: Annotated[
        bool,
        Query(description="Return only editor-recommended places"),
    ] = False,
    sort: Annotated[
        str,
        Query(
            description="rating_desc (default) | rating_asc | name | price_asc | price_desc | reviews_desc"
        ),
    ] = place_service.DEFAULT_SORT,
) -> PlaceSearchResponse:
    """Search places with optional filters and pagination.

    Unknown cities return ``total: 0`` (not a 404). ``min_rating`` and
    ``price_level`` accept empty strings as "no filter".
    ``total`` reflects the full match count; ``results`` is the current page.
    """
    min_rating_val: float | None = None
    if min_rating:
        try:
            min_rating_val = float(min_rating)
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="min_rating must be a number between 0 and 5",
            ) from None
        if not (0 <= min_rating_val <= 5):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="min_rating must be between 0 and 5",
            )

    price_level_val: int | None = None
    if price_level:
        try:
            price_level_val = int(price_level)
        except ValueError:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="price_level must be an integer between 1 and 4",
            ) from None
        if not (1 <= price_level_val <= 4):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="price_level must be between 1 and 4",
            )

    if category and category.lower() not in VALID_CATEGORIES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category '{category}'. Valid: {sorted(VALID_CATEGORIES)}",
        )
    if sort not in VALID_SORTS:
        sort = place_service.DEFAULT_SORT

    all_results = place_service.search_places(
        city=city,
        category=category,
        min_rating=min_rating_val,
        price_level=price_level_val,
        recommended_only=recommended,
        sort=sort,
    )
    page, total = pagination.page_of(all_results)
    return PlaceSearchResponse(
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        city=city,
        category=category,
        min_rating=min_rating_val,
        price_level=price_level_val,
        recommended_only=recommended,
        sort=sort,
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


@router.get(
    "/{place_id}",
    response_model=Place,
    summary="Get a single place by ID",
)
def get_place(place_id: str) -> Place:
    """Return a single place, or 404 if the ID does not exist."""
    place = place_service.get_place(place_id)
    if place is None:
        raise NotFoundError("Place not found")
    return place
