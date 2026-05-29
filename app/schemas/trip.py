"""Trip (itinerary) schemas.

A ``Trip`` is the one aggregate the Travel Planner agent builds up over a
conversation: a named destination with dates, the flight/hotel bookings it
has made, and an ordered list of places to visit. It is mutable state —
persisted to SQLite alongside bookings — so the agent can create it, fetch
it back, and amend it as the plan evolves.

``Trip`` is the canonical resource (booking/place references are IDs).
``TripDetail`` is the expanded one-call view returned by ``GET /trips/{id}``:
it resolves those references to full ``Booking`` and ``Place`` objects so an
agent doesn't have to fan out a dozen follow-up requests.
"""

from datetime import datetime

from pydantic import Field, computed_field

from app.core.codes import prefixed_code
from app.enums import TripStatus
from app.schemas.base import AppBaseModel, RequestModel
from app.schemas.booking import Booking
from app.schemas.pagination import PagedResponse
from app.schemas.place import Place

# Prefix for the friendly trip short code, e.g. "TRP-AB23XY".
TRIP_CODE_PREFIX = "TRP"


def trip_confirmation_code(trip_id: str) -> str:
    """Derive the stable ``TRP-XXXXXX`` reference for a trip ID."""
    return prefixed_code(TRIP_CODE_PREFIX, trip_id)


class TripItem(RequestModel):
    """One stop on the itinerary — a place, optionally pinned to a day.

    Extends ``RequestModel`` so a typo in a nested item field (in a create or
    update body) is rejected rather than silently dropped, the same as the
    top-level request.
    """

    place_id: str = Field(
        description="Canonical place ID or PLC-XXXXXX short code to visit.",
        examples=["56f5b6d7-f0e2-5867-a9dd-087a98cff34c"],
    )
    day: int | None = Field(
        default=None,
        ge=1,
        description="1-based day of the trip this stop falls on (optional).",
        examples=[1],
    )
    note: str | None = Field(
        default=None,
        description="Free-form note for this stop — e.g. 'sunset', 'lunch'.",
        examples=["Catch the sunset"],
    )


class TripItemDetail(TripItem):
    """An itinerary stop with its referenced place resolved in full."""

    place: Place | None = Field(
        default=None,
        description="The resolved place, or null if the ID no longer exists.",
    )


class Trip(AppBaseModel):
    """A planned trip — the agent's itinerary aggregate.

    ``id`` is the canonical UUID (used in URLs); ``confirmation_code`` is the
    friendly ``TRP-XXXXXX`` reference either of which is accepted by
    ``GET /trips/{id}``.
    """

    id: str = Field(
        description="Canonical trip UUID. Accepted by /trips/{id}.",
        examples=["b2c3d4e5-6f70-5182-93a4-b5c6d7e8f901"],
    )
    name: str = Field(
        description="Human name for the trip.", examples=["Da Nang long weekend"]
    )
    destination_city: str = Field(
        description="Canonical destination city (resolved).", examples=["Da Nang"]
    )
    country: str = Field(
        description="Country, derived from the city.", examples=["Vietnam"]
    )
    start_date: str = Field(
        description="Trip start date, YYYY-MM-DD.", examples=["2026-06-01"]
    )
    end_date: str = Field(
        description="Trip end date, YYYY-MM-DD.", examples=["2026-06-04"]
    )
    booking_ids: list[str] = Field(
        description="Canonical IDs of the flight/hotel bookings attached to this trip.",
    )
    items: list[TripItem] = Field(
        description="Ordered itinerary stops (places to visit).",
    )
    status: TripStatus = Field(
        default=TripStatus.PLANNING,
        description="'planning' (default), 'booked', or 'cancelled'.",
    )
    notes: str | None = Field(
        default=None, description="Free-form note an agent or user attached."
    )
    created_at: datetime = Field(description="When the trip was created (UTC).")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def confirmation_code(self) -> str:
        """Friendly ``TRP-XXXXXX`` reference, derived from ``id``."""
        return trip_confirmation_code(self.id)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def nights(self) -> int:
        """Number of nights between start and end (0 for a same-day trip)."""
        fmt = "%Y-%m-%d"
        try:
            delta = datetime.strptime(self.end_date, fmt) - datetime.strptime(
                self.start_date, fmt
            )
            return max(delta.days, 0)
        except ValueError:
            return 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def summary(self) -> str:
        """One-line human/agent-readable description of the trip."""
        return (
            f"{self.name} · {self.destination_city}, {self.country} · "
            f"{self.start_date}→{self.end_date} · "
            f"{len(self.booking_ids)} booking(s), {len(self.items)} place(s)"
        )


class TripDetail(Trip):
    """A trip with its booking and place references resolved in full.

    Returned by ``GET /trips/{id}`` so an agent gets the whole plan — the
    attached bookings and the itinerary places — in a single call.
    """

    bookings: list[Booking] = Field(
        description="The bookings referenced by `booking_ids`, resolved."
    )
    itinerary: list[TripItemDetail] = Field(
        description="`items` with each referenced place resolved in full."
    )


# --- Requests ----------------------------------------------------------------


class TripCreateRequest(RequestModel):
    """Request body for ``POST /trips``.

    ``destination_city`` is matched fuzzily; ``booking_ids`` and ``items``
    are validated to reference existing bookings/places. Dates must be valid
    ``YYYY-MM-DD`` with ``end_date`` on or after ``start_date``.
    """

    name: str = Field(
        description="Human name for the trip.", examples=["Da Nang long weekend"]
    )
    destination_city: str = Field(
        description="Destination city (fuzzy — typo/case tolerant).",
        examples=["Da Nang"],
    )
    start_date: str = Field(
        description="Trip start date, YYYY-MM-DD.", examples=["2026-06-01"]
    )
    end_date: str = Field(
        description="Trip end date, YYYY-MM-DD.", examples=["2026-06-04"]
    )
    booking_ids: list[str] = Field(
        default_factory=list,
        description="Existing booking UUIDs or confirmation codes to attach.",
    )
    items: list[TripItem] = Field(
        default_factory=list, description="Initial itinerary stops."
    )
    notes: str | None = Field(default=None, description="Free-form note.")


class TripUpdateRequest(RequestModel):
    """Request body for ``PATCH /trips/{id}`` — every field optional.

    Only the fields present in the request are changed (a partial update);
    omit a field to leave it untouched. Send ``status: "cancelled"`` to
    cancel, or use ``DELETE /trips/{id}``.
    """

    name: str | None = Field(default=None, description="New trip name.")
    destination_city: str | None = Field(
        default=None, description="New destination city (fuzzy)."
    )
    start_date: str | None = Field(
        default=None, description="New start date, YYYY-MM-DD."
    )
    end_date: str | None = Field(default=None, description="New end date, YYYY-MM-DD.")
    booking_ids: list[str] | None = Field(
        default=None, description="Replacement list of attached booking references."
    )
    items: list[TripItem] | None = Field(
        default=None, description="Replacement itinerary stops."
    )
    status: TripStatus | None = Field(default=None, description="New status.")
    notes: str | None = Field(default=None, description="New note.")


class TripListResponse(PagedResponse[Trip]):
    """Response body for ``GET /trips``."""
