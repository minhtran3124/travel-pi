"""Destination overview schema — a one-call snapshot of a city.

Aggregates what an LLM travel agent needs to start reasoning about a
destination — top places, essential tips, live weather, hotel count, and the
serving airports — so it can replace four or five separate calls with one.
"""

from pydantic import Field

from app.schemas.airport import Airport
from app.schemas.base import AppBaseModel
from app.schemas.place import Place
from app.schemas.tip import Tip
from app.schemas.weather import WeatherResponse


class DestinationOverview(AppBaseModel):
    """Everything an agent needs to size up a destination in one response."""

    city: str = Field(
        description="Canonical city name (resolved).", examples=["Da Nang"]
    )
    country: str = Field(description="Country.", examples=["Vietnam"])
    latitude: float | None = Field(
        default=None, description="Latitude, decimal degrees."
    )
    longitude: float | None = Field(
        default=None, description="Longitude, decimal degrees."
    )
    airports: list[Airport] = Field(
        description="Airports serving this city (may be empty)."
    )
    hotel_count: int = Field(
        description="Number of hotels in the seed data for this city.", examples=[5]
    )
    top_places: list[Place] = Field(
        description="Highest-rated places in the city (capped by `top_places`)."
    )
    essential_tips: list[Tip] = Field(
        description="The must-know local tips for this destination."
    )
    weather: WeatherResponse | None = Field(
        default=None,
        description=(
            "Current conditions + short forecast. Best-effort: null if the "
            "live weather provider was unreachable (the rest is still returned)."
        ),
    )
    summary: str = Field(
        description="One-line human/agent-readable description of the destination."
    )
