"""Canonical OpenAPI tags for the routers.

``str, Enum`` base (not ``enum.StrEnum``, which is 3.11+) keeps this importable
on the project's ``py310`` target.
"""

from enum import Enum


class Tags(str, Enum):
    """Tag names used in ``APIRouter(tags=[...])``; value == the tag string."""

    airports = "airports"
    cities = "cities"
    flights = "flights"
    hotels = "hotels"
    places = "places"
    tips = "tips"
    destinations = "destinations"
    currency = "currency"
    visa = "visa"
    weather = "weather"
    air_quality = "air-quality"
    bookings = "bookings"
    trips = "trips"
    expenses = "expenses"
    health = "health"
    meta = "meta"
    dashboard = "dashboard"
    agent = "agent"
    admin = "admin"
