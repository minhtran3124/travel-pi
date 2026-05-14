"""Pydantic request/response models exposed through the OpenAPI schema."""

from app.schemas.airport import Airport, AirportListResponse
from app.schemas.booking import Booking, BookingListResponse
from app.schemas.city import City, CityListResponse
from app.schemas.flight import (
    Airline,
    Flight,
    FlightBookingRequest,
    FlightSearchInfo,
    FlightSearchResponse,
)
from app.schemas.hotel import (
    Hotel,
    HotelBookingRequest,
    HotelListResponse,
    HotelSearchInfo,
    HotelSearchResponse,
)
from app.schemas.meta import ServiceInfo
from app.schemas.pagination import PagedResponse, PaginationDep, PaginationParams
from app.schemas.place import Place, PlaceListResponse, PlaceSearchResponse

__all__ = [
    "Airport",
    "AirportListResponse",
    "Booking",
    "BookingListResponse",
    "City",
    "CityListResponse",
    "Airline",
    "Flight",
    "FlightBookingRequest",
    "FlightSearchInfo",
    "FlightSearchResponse",
    "Hotel",
    "HotelBookingRequest",
    "HotelListResponse",
    "HotelSearchInfo",
    "HotelSearchResponse",
    "PagedResponse",
    "PaginationDep",
    "PaginationParams",
    "Place",
    "PlaceListResponse",
    "PlaceSearchResponse",
    "ServiceInfo",
]
