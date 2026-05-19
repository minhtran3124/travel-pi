"""Place / attraction schemas."""

from pydantic import Field, computed_field

from app.core.codes import prefixed_code
from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse

# Prefix used for the friendly place short code, e.g. "PLC-AB23XY".
PLACE_CODE_PREFIX = "PLC"


class Place(AppBaseModel):
    """A point of interest — attraction, restaurant, café, activity, etc."""

    id: str = Field(
        description=(
            "Canonical place ID (UUID). Accepted by GET /places/{place_id}; "
            "see `short_code` for a friendlier alternative."
        ),
        examples=["56f5b6d7-f0e2-5867-a9dd-087a98cff34c"],
    )
    name: str = Field(description="Place name.", examples=["Dragon Bridge"])
    city: str = Field(description="City (display case).", examples=["Da Nang"])
    country: str = Field(description="Country.", examples=["Vietnam"])
    category: str = Field(
        description=(
            "One of: 'attraction', 'restaurant', 'cafe', 'activity', "
            "'nightlife', 'shopping'. Call GET /places/categories for the "
            "live list."
        ),
        examples=["attraction"],
    )
    description: str = Field(description="Short description of the place.")
    address: str = Field(description="Street address.")
    rating: float = Field(
        ge=0, le=5, description="Average user rating, 0–5.", examples=[4.7]
    )
    review_count: int = Field(description="Number of user reviews.")
    price_level: int = Field(
        ge=1,
        le=4,
        description="Price band: 1 = free/cheap, 2 = moderate, 3 = expensive, 4 = luxury.",
        examples=[2],
    )
    opening_hours: str | None = Field(
        default=None,
        description="Free-text opening hours (best-effort, may be None).",
        examples=["Mon-Sun 09:00-22:00"],
    )
    image_url: str = Field(description="URL of a representative image.")
    tags: list[str] = Field(
        description="Free-form descriptor tags.",
        examples=[["family-friendly", "outdoor"]],
    )
    is_recommended: bool = Field(
        default=False,
        description="Curated 'must-see' flag — true for editor-picked highlights.",
    )
    latitude: float | None = Field(
        default=None, description="Latitude in decimal degrees (WGS-84)."
    )
    longitude: float | None = Field(
        default=None, description="Longitude in decimal degrees (WGS-84)."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def short_code(self) -> str:
        """Friendly ``PLC-XXXXXX`` reference derived from ``id``.

        Accepted anywhere a ``place_id`` is — easier to read aloud or quote
        in a chat message than the raw UUID.
        """
        return prefixed_code(PLACE_CODE_PREFIX, self.id)


class NearbyPlace(Place):
    """A place plus its straight-line distance from the query origin."""

    distance_km: float = Field(
        description="Straight-line distance from the origin place, in kilometres.",
        examples=[0.84],
    )


class PlaceNearbyResponse(AppBaseModel):
    """Response body for ``GET /places/nearby``.

    ``results`` is ordered nearest-first and excludes the origin place
    itself. ``count`` is the number returned (after the ``limit`` cap).
    """

    origin_place_id: str = Field(
        description="The place_id (or short code) the search anchored on."
    )
    radius_km: float = Field(description="Search radius used, in kilometres.")
    count: int = Field(description="Number of places returned.")
    results: list[NearbyPlace]


class PlaceListResponse(PagedResponse[Place]):
    """Response body for ``GET /places`` (paginated list of all places)."""


class PlaceSearchResponse(PagedResponse[Place]):
    """Response body for ``GET /places/search``."""

    city: str | None = Field(default=None, description="City filter applied.")
    category: str | None = Field(default=None, description="Category filter applied.")
    min_rating: float | None = Field(default=None, description="Min-rating filter applied.")
    price_level: int | None = Field(default=None, description="Price-level filter applied.")
    recommended_only: bool = Field(
        default=False, description="True if only `is_recommended` places were returned."
    )
    sort: str = Field(
        default="rating_desc",
        description=(
            "Sort key applied. One of: 'rating_desc', 'rating_asc', "
            "'name', 'price_asc', 'price_desc', 'reviews_desc'."
        ),
    )
