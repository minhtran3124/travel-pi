"""Aggregate router — wires every endpoint group into a single router.

``app.main.create_app`` includes just this one router, so adding or removing
an endpoint group is a one-line change here instead of touching the app
factory.
"""

from fastapi import APIRouter

from app.routers import (
    airports,
    bookings,
    cities,
    dashboard,
    destinations,
    flights,
    hotels,
    meta,
    places,
    tips,
    trips,
    weather,
)

router = APIRouter()

# Order is cosmetic — it sets the Swagger tag order.
router.include_router(meta.router)
router.include_router(airports.router)
router.include_router(cities.router)
router.include_router(flights.router)
router.include_router(hotels.router)
router.include_router(places.router)
router.include_router(tips.router)
router.include_router(weather.router)
router.include_router(destinations.router)
router.include_router(bookings.router)
router.include_router(trips.router)
# Server-rendered HTML dashboard — excluded from the OpenAPI schema.
router.include_router(dashboard.router)
