"""Saved (user/agent-created) place schemas — the mutable POI overlay."""

from pydantic import Field, computed_field

from app.core.codes import prefixed_code
from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse
from app.schemas.place import Place

SAVED_PLACE_CODE_PREFIX = "SPL"


class SavedPlaceCreate(AppBaseModel):
    name: str = Field(
        min_length=1, description="POI name.", examples=["Secret rooftop bar"]
    )
    city: str | None = Field(default=None, examples=["Hanoi"])
    country: str | None = None
    category: str | None = Field(default=None, examples=["nightlife"])
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    price_level: int | None = Field(default=None, ge=1, le=4, examples=[2])
    notes: str | None = None
    links: list[str] | None = Field(
        default=None, examples=[["https://maps.app.goo.gl/x"]]
    )
    duration: int | None = Field(
        default=None, ge=0, description="Typical visit minutes."
    )
    favorite: bool = False
    visited: bool = False


class SavedPlace(SavedPlaceCreate):
    id: str = Field(description="Saved-place UUID.")
    created_at: str = Field(description="ISO-8601 creation timestamp.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def short_code(self) -> str:
        """Friendly ``SPL-XXXXXX`` reference (mirrors catalog ``PLC-``)."""
        return prefixed_code(SAVED_PLACE_CODE_PREFIX, self.id)


class SavedPlaceFlag(AppBaseModel):
    """Body for the favorite/visited SET endpoints (idempotent)."""

    value: bool = Field(description="Target flag value.", examples=[True])


class SavedPlaceListResponse(PagedResponse[SavedPlace]):
    """Response body for ``GET /places/saved``."""


class ShortlistEntry(AppBaseModel):
    """One place on a trip's shortlist (catalog or saved), resolved."""

    link_id: str = Field(description="trip_place_link id — the handle for DELETE.")
    source: str = Field(description="'catalog' or 'saved'.", examples=["catalog"])
    place: Place | SavedPlace = Field(
        description="Resolved place; `source` says which model."
    )
