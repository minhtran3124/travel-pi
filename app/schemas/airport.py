"""Airport schemas."""

from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse


class Airport(AppBaseModel):
    """A supported airport."""

    code: str  # IATA 3-letter code, e.g. "DAD"
    name: str  # e.g. "Da Nang International Airport"
    city: str  # e.g. "Da Nang"
    country: str  # e.g. "Vietnam"


class AirportListResponse(PagedResponse[Airport]):
    """Response body for ``GET /airports``."""
