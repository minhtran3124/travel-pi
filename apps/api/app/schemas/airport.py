"""Airport schemas."""

from pydantic import Field

from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse


class Airport(AppBaseModel):
    """A supported airport."""

    code: str = Field(
        description=(
            "3-letter IATA airport code, uppercase. Pass this as `origin` "
            "or `destination` on /flights/search."
        ),
        examples=["DAD"],
    )
    name: str = Field(
        description="Full airport name.",
        examples=["Da Nang International Airport"],
    )
    city: str = Field(description="City served by the airport.", examples=["Da Nang"])
    country: str = Field(description="Country.", examples=["Vietnam"])


class AirportListResponse(PagedResponse[Airport]):
    """Response body for ``GET /airports``."""
