"""Hotel endpoints: search, detail, and booking."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status

from app.core.auth import CurrentUserDep, require_premium
from app.exceptions import NotFoundError
from app.routers.tags import Tags
from app.schemas.booking import Booking
from app.schemas.error import error_responses
from app.schemas.hotel import (
    Hotel,
    HotelAvailabilityInfo,
    HotelAvailabilityResponse,
    HotelBookingRequest,
    HotelListResponse,
    HotelSearchInfo,
    HotelSearchResponse,
)
from app.schemas.pagination import PaginationDep
from app.services.booking_service import BookingService, get_booking_service
from app.services.hotel_service import HotelService, get_hotel_service

router = APIRouter(prefix="/hotels", tags=[Tags.hotels], responses=error_responses(422))

BookingsDep = Annotated[BookingService, Depends(get_booking_service)]
HotelDep = Annotated[HotelService, Depends(get_hotel_service)]


@router.get(
    "",
    response_model=HotelListResponse,
    summary="List all hotels (paginated)",
)
def list_hotels(pagination: PaginationDep, hotels: HotelDep) -> HotelListResponse:
    """Return all seeded hotels with pagination.

    ``total`` is the full count; use ``limit`` and ``offset`` to page.

    :param pagination: The pagination params (limit/offset).
    :param hotels: The hotel service.
    :return: The seeded hotels, paginated.
    """
    page, total = pagination.page_of(hotels.list_hotels())
    return HotelListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )


# Required amenities, shared by /search and /availability. No default here —
# FastAPI requires the default to be set with ``= None`` at the call site.
_AMENITIES_QUERY = Query(
    description=(
        "Required amenities (all must match). Repeat the param for multiple "
        "values, e.g. ?amenities=Pool&amenities=Spa"
    ),
    examples=["Pool"],
)


# Note: declare "/search" before "/{hotel_id}" so it is not captured as an ID.
@router.get(
    "/search",
    response_model=HotelSearchResponse,
    summary="Browse hotels in a city (no dates — discovery)",
)
def search_hotels(
    pagination: PaginationDep,
    hotels: HotelDep,
    city: Annotated[
        str,
        Query(
            description="City name — fuzzy (typo/case tolerant)",
            examples=["Da Nang"],
        ),
    ],
    min_stars: Annotated[
        int | None,
        Query(ge=1, le=5, description="Minimum star rating (1–5)", examples=[4]),
    ] = None,
    max_price: Annotated[
        float | None,
        Query(ge=0, description="Maximum price per night (USD)", examples=[150]),
    ] = None,
    amenities: Annotated[list[str] | None, _AMENITIES_QUERY] = None,
) -> HotelSearchResponse:
    """Browse the hotels in a city — pure discovery, no dates needed.

    Answers "are there any hotels in this city" and lets the client filter
    by stars / price / amenities. To check whether rooms are actually free
    for specific dates, use ``GET /hotels/availability``. Unknown cities
    return ``total: 0`` (not a 404).

    :param pagination: The pagination params (limit/offset).
    :param hotels: The hotel service.
    :param city: City name — fuzzy (typo/case tolerant).
    :param min_stars: Optional minimum star rating (1-5).
    :param max_price: Optional maximum price per night (USD).
    :param amenities: Optional required amenities (all must match).
    :return: The matching hotels, paginated.
    """
    all_results = hotels.search_hotels(
        city, min_stars=min_stars, max_price=max_price, amenities=amenities
    )
    page, total = pagination.page_of(all_results)
    # Echo the canonical city name when the fuzzy lookup resolved it.
    echoed_city = hotels.resolve_city(city) or city
    return HotelSearchResponse(
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        search=HotelSearchInfo(
            city=echoed_city,
            min_stars=min_stars,
            max_price=max_price,
            amenities=amenities,
        ),
        results=page,
    )


# Note: declare "/availability" before "/{hotel_id}" so it is not an ID.
@router.get(
    "/availability",
    response_model=HotelAvailabilityResponse,
    summary="Check room availability for specific dates and party size",
)
def hotel_availability(
    pagination: PaginationDep,
    hotels: HotelDep,
    city: Annotated[
        str,
        Query(
            description="City name — fuzzy (typo/case tolerant)",
            examples=["Da Nang"],
        ),
    ],
    check_in: Annotated[
        str,
        Query(description="Check-in date, YYYY-MM-DD", examples=["2026-06-01"]),
    ],
    check_out: Annotated[
        str,
        Query(description="Check-out date, YYYY-MM-DD", examples=["2026-06-03"]),
    ],
    rooms: Annotated[int, Query(ge=1, description="Rooms needed", examples=[1])] = 1,
    adults: Annotated[
        int, Query(ge=1, description="Adults in the party", examples=[2])
    ] = 2,
    children: Annotated[
        int, Query(ge=0, description="Children in the party", examples=[0])
    ] = 0,
    available_only: Annotated[
        bool,
        Query(
            description="Return only hotels that can take the booking",
            examples=[True],
        ),
    ] = False,
    min_stars: Annotated[
        int | None,
        Query(ge=1, le=5, description="Minimum star rating (1–5)", examples=[4]),
    ] = None,
    max_price: Annotated[
        float | None,
        Query(ge=0, description="Maximum price per night (USD)", examples=[150]),
    ] = None,
    amenities: Annotated[list[str] | None, _AMENITIES_QUERY] = None,
) -> HotelAvailabilityResponse:
    """Check, for specific dates and party size, which hotels have rooms.

    Each result carries ``available`` (enough rooms *and* they can hold the
    party), the free-room count, per-room capacity, and the all-in
    ``total_price`` (``price_per_night × nights × rooms``). With
    ``available_only=true`` the unavailable hotels are dropped. Unknown
    cities return ``total: 0``; a bad date is **422**.

    :param pagination: The pagination params (limit/offset).
    :param hotels: The hotel service.
    :param city: City name — fuzzy (typo/case tolerant).
    :param check_in: Check-in date, YYYY-MM-DD.
    :param check_out: Check-out date, YYYY-MM-DD.
    :param rooms: Rooms needed.
    :param adults: Adults in the party.
    :param children: Children in the party.
    :param available_only: Whether to return only hotels that can take the booking.
    :param min_stars: Optional minimum star rating (1-5).
    :param max_price: Optional maximum price per night (USD).
    :param amenities: Optional required amenities (all must match).
    :return: The availability check results, paginated.
    """
    try:
        nights, results = hotels.check_availability(
            city,
            check_in,
            check_out,
            rooms=rooms,
            adults=adults,
            children=children,
            min_stars=min_stars,
            max_price=max_price,
            amenities=amenities,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid check_in/check_out; expected format YYYY-MM-DD",
        ) from exc

    if available_only:
        results = [r for r in results if r.available]

    page, total = pagination.page_of(results)
    echoed_city = hotels.resolve_city(city) or city
    return HotelAvailabilityResponse(
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        search=HotelAvailabilityInfo(
            city=echoed_city,
            check_in=check_in,
            check_out=check_out,
            nights=nights,
            rooms=rooms,
            adults=adults,
            children=children,
            min_stars=min_stars,
            max_price=max_price,
            amenities=amenities,
        ),
        results=page,
    )


@router.get(
    "/{hotel_id}",
    response_model=Hotel,
    summary="Get a single hotel by ID",
    responses=error_responses(404),
)
def get_hotel(
    hotels: HotelDep,
    hotel_id: Annotated[
        str,
        Path(
            description="Hotel UUID from /hotels or /hotels/search",
            examples=["5c1a8d2c-5e1c-4d6f-9a73-2c3b9b0a4ac5"],
        ),
    ],
) -> Hotel:
    """Return a single hotel, or 404 if the ID does not exist.

    :param hotels: The hotel service.
    :param hotel_id: Hotel UUID from ``/hotels`` or ``/hotels/search``.
    :return: The matching hotel.
    """
    hotel = hotels.get_hotel(hotel_id)
    if hotel is None:
        raise NotFoundError(
            f"Hotel {hotel_id!r} not found",
            hint=(
                "Use GET /hotels/search?city=<city> or GET /hotels to find "
                "a valid hotel_id, or pass the short HTL-XXXX code."
            ),
        )
    return hotel


@router.post(
    "/book",
    response_model=Booking,
    summary="Create a hotel booking",
    responses=error_responses(403, 404, 409),
    dependencies=[Depends(require_premium)],
)
def book_hotel(
    request: HotelBookingRequest,
    bookings: BookingsDep,
    auth_user: CurrentUserDep,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description=(
                "Optional client-supplied key that makes this POST "
                "replay-safe: repeating the request with the same key "
                "returns the original booking instead of creating a "
                "duplicate."
            ),
            examples=["booking-2026-06-01-abc123"],
        ),
    ] = None,
) -> Booking:
    """Create a hotel booking, or replay an earlier one for the same key.

    ``total_price`` is computed server-side.

    :param request: The booking request body.
    :param bookings: The booking service.
    :param auth_user: The authenticated caller, stamped as the booking owner.
    :param idempotency_key: Optional client-supplied key that makes this
        POST replay-safe.
    :return: The created (or replayed) booking.
    """
    return bookings.book_hotel(
        request, user_id=auth_user.id, idempotency_key=idempotency_key
    )
