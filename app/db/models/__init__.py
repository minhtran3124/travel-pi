"""ORM models package. Reference via the namespace: `models.Hotel`, `models.Booking`.

Class names intentionally match app/schemas Pydantic models — disambiguate by import
(`from app.db import models` → models.X) vs (`from app.schemas.x import X`).
"""

from app.db.models.booking import Booking
from app.db.models.flight_index import FlightIndex
from app.db.models.saved_place import SavedPlace
from app.db.models.trip import Trip, TripItem, TripPlaceLink

# Chunk B appends: Country, Airline, Airport, City, Hotel, Place, Tip, CountrySummary,
# Visa, FxRate, CountryCurrency, FxMeta

__all__ = [
    "Booking",
    "Trip",
    "TripItem",
    "TripPlaceLink",
    "SavedPlace",
    "FlightIndex",
]
