"""Trip itinerary schemas — a freeform, day-by-day plan and its items.

Trips are the second mutable state in the API (alongside bookings): a user or
agent assembles a day-by-day plan of places, activities, meals, transport legs,
and notes. This is standalone planning storage — items are freeform and are
*not* linked to bookings or validated against the place catalog.
"""

from datetime import date, datetime
from typing import Annotated

from pydantic import Field, model_validator

from app.enums import ActivityLevel, MealStyle, TripItemKind, TripItemStatus
from app.schemas.base import AppBaseModel
from app.schemas.pagination import PagedResponse
from app.schemas.saved_place import ShortlistEntry


class TripItemCreate(AppBaseModel):
    """Request body for adding or replacing an itinerary item."""

    day: int = Field(
        ge=1, description="1-based day number within the trip.", examples=[1]
    )
    kind: TripItemKind = Field(description="Item kind.", examples=["place"])
    status: TripItemStatus = Field(
        default=TripItemStatus.PENDING,
        description=(
            "Planning state: pending (default), booked, constraint, or optional. "
            "Optional items are excluded from itinerary gap-detection."
        ),
        examples=["pending"],
    )
    title: str = Field(
        min_length=1,
        max_length=200,
        description="Short label, e.g. 'Marble Mountains'.",
    )
    sort_order: int = Field(
        default=0, ge=0, description="Ordering within the day (ascending)."
    )
    place_id: str | None = Field(
        default=None,
        description="Optional free-text reference to a place. Not validated against the catalog.",
    )
    booking_id: str | None = Field(
        default=None,
        description=(
            "Optional link to a booking (/bookings UUID or confirmation_code) whose "
            "price rolls up into the trip's total_spent. Not validated at write time."
        ),
        examples=["BK-ABCD1234"],
    )
    start_time: str | None = Field(
        default=None, description="Optional local start time, e.g. '09:00'."
    )
    notes: str | None = Field(
        default=None, max_length=1000, description="Optional free-form note."
    )


class TripItemUpdate(TripItemCreate):
    """Request body for replacing an item (same shape as create)."""


class TripItem(TripItemCreate):
    """An itinerary item as stored and returned."""

    id: str = Field(description="Item UUID.")
    trip_id: str = Field(description="Owning trip UUID.")


class TripCreate(AppBaseModel):
    """Request body for creating a trip."""

    title: str = Field(
        min_length=1,
        max_length=200,
        description="Trip title, e.g. 'Da Nang long weekend'.",
    )
    city: str | None = Field(
        default=None,
        max_length=120,
        description="Primary destination city (free text).",
    )
    start_date: date | None = Field(
        default=None, description="Trip start date (YYYY-MM-DD)."
    )
    end_date: date | None = Field(
        default=None, description="Trip end date (YYYY-MM-DD)."
    )
    travelers: int = Field(default=1, ge=1, le=50, description="Number of travelers.")
    notes: str | None = Field(
        default=None, max_length=2000, description="Free-form trip note."
    )
    items: list[TripItemCreate] = Field(
        default_factory=list, description="Optional initial itinerary items."
    )

    @model_validator(mode="after")
    def _check_dates(self) -> "TripCreate":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class TripUpdate(AppBaseModel):
    """Request body for replacing a trip's top-level fields.

    PUT semantics: every top-level field is replaced. Omitted optional fields
    reset to their defaults. Items are managed via the item sub-resource
    endpoints, not here.
    """

    title: str = Field(min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    travelers: int = Field(default=1, ge=1, le=50)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check_dates(self) -> "TripUpdate":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class Trip(AppBaseModel):
    """A trip itinerary with its day-by-day items (sorted by day, then order)."""

    id: str = Field(description="Trip UUID.")
    title: str
    city: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    travelers: int
    notes: str | None = None
    created_at: datetime = Field(description="When the trip was created (UTC).")
    items: list[TripItem] = Field(default_factory=list)


class TripDetail(Trip):
    """A trip with computed value-layer fields (returned by detail / day-plan endpoints)."""

    total_spent: float = Field(
        description="Sum of linked, non-cancelled booking prices (USD)."
    )
    remaining_budget: float | None = Field(
        default=None,
        description="Total budget cap minus total_spent (USD); negative when over "
        "budget, null when no per-category cap is set. Same value as "
        "GET /trips/{id}/budget's total_remaining, surfaced here so the rollup is "
        "available in one call.",
        examples=[400.0],
    )
    gaps: list[str] = Field(
        default_factory=list,
        description="Human-readable coverage gaps, e.g. 'Day 3 has no accommodation'.",
    )
    places: list[ShortlistEntry] = Field(
        default_factory=list,
        description="The trip's shortlisted places (catalog or saved), each resolved.",
    )


class AddTripPlaceRequest(AppBaseModel):
    """Request body for shortlisting a place onto a trip."""

    place_id: str = Field(
        description="Catalog place id (UUID/PLC-) or saved_places id.",
        examples=["PLC-AB23XY"],
    )
    source: str = Field(
        default="catalog",
        description="'catalog' (seed) or 'saved' (the saved-places store).",
        examples=["catalog"],
    )


class DayPlanItem(AppBaseModel):
    """One itinerary item plus optional travel info to the next item."""

    item: TripItem
    travel_to_next_minutes: float | None = Field(
        default=None,
        description="Estimated travel time to the next item in minutes.",
    )
    travel_to_next_mode: str | None = Field(
        default=None,
        description="Travel mode to the next item, e.g. 'driving', 'walking'.",
    )


class DayPlanResponse(AppBaseModel):
    """Response body for a single day's itinerary."""

    trip_id: str = Field(description="Owning trip UUID.")
    date: Annotated[date, Field(description="Calendar date for this day (YYYY-MM-DD).")]
    day: int = Field(description="1-based day number within the trip.")
    items: list[DayPlanItem] = Field(
        default_factory=list, description="Ordered list of items for this day."
    )
    weather_score: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Day suitability 0–1 derived from the forecast (higher = better for "
            "outdoor activities). None when the trip has no city, the date is "
            "outside the forecast window, or weather is unavailable."
        ),
    )


class TripListResponse(PagedResponse[Trip]):
    """Response body for ``GET /trips``."""


class TripEstimateRequest(AppBaseModel):
    """Request body for ``POST /trips/estimate`` — pure calculation, no state."""

    city: str | None = Field(
        default=None,
        max_length=120,
        description="Destination city (free text). Informational; does not affect the math.",
    )
    nights: int = Field(ge=1, description="Number of nights.", examples=[3])
    travelers: int = Field(
        ge=1, le=50, description="Number of travelers.", examples=[2]
    )
    flight_total_usd: float | None = Field(
        default=None,
        ge=0,
        description="Known total flight cost in USD (e.g. from /flights/search). Omit to exclude.",
    )
    hotel_price_per_night_usd: float | None = Field(
        default=None,
        ge=0,
        description="Known room price per night in USD (e.g. from /hotels/availability). Omit to exclude.",
    )
    meal_style: MealStyle = Field(default=MealStyle.MID, description="Meal-spend tier.")
    activity_level: ActivityLevel = Field(
        default=ActivityLevel.SOME, description="Activity-spend tier."
    )


class EstimateBreakdown(AppBaseModel):
    """Per-category USD figures that sum to the subtotal."""

    flights: float
    accommodation: float
    meals: float
    activities: float
    local_transport: float


class TripEstimateResponse(AppBaseModel):
    """Response body for ``POST /trips/estimate``."""

    currency: str = Field(default="USD", description="Always USD in this mock.")
    city: str | None = Field(
        default=None, description="Echo of the request city, if given."
    )
    nights: int
    travelers: int
    breakdown: EstimateBreakdown
    subtotal: float = Field(description="Sum of the breakdown lines (USD).")
    buffer_pct: int = Field(description="Incidentals buffer applied, as a percent.")
    total_estimate: float = Field(
        description="Subtotal + buffer, rounded to whole USD."
    )
    per_person: float = Field(description="total_estimate / travelers (USD, 2 dp).")
    assumptions: list[str] = Field(
        description="Plain-language statement of every rate and choice used."
    )
    notes: str = Field(description="Scope caveat for the estimate.")


class CategoryBudget(AppBaseModel):
    """Cap (the planned target) vs spent (booked rollup) for one category."""

    cap: float | None = Field(
        default=None,
        description="The budget cap for this category in USD, or null if unset.",
        examples=[700.0],
    )
    spent: float = Field(
        description="Booked spend in this category (USD): linked, non-cancelled "
        "bookings of the matching type. 0 for categories with no booking source.",
        examples=[600.0],
    )
    remaining: float | None = Field(
        default=None,
        description="cap - spent (USD); negative when over. null when no cap is set.",
        examples=[100.0],
    )


class BudgetCategories(AppBaseModel):
    """The four canonical spend buckets, each a cap/spent/remaining triple."""

    flights: CategoryBudget
    hotels: CategoryBudget
    activities: CategoryBudget
    buffer: CategoryBudget


class TripBudget(AppBaseModel):
    """Response for GET/POST /trips/{id}/budget — per-category caps vs spend."""

    trip_id: str = Field(description="Owning trip UUID.")
    categories: BudgetCategories = Field(
        description="Per-category cap vs spent vs remaining."
    )
    total_cap: float | None = Field(
        default=None,
        description="Sum of set caps (USD), or null if no cap is set anywhere.",
    )
    total_spent: float = Field(description="Sum of category spend (USD).")
    booked_total: float = Field(
        description="Sum of every non-cancelled booking carrying this trip's "
        "trip_id, counted once each — independent of total_spent, which "
        "walks itinerary items instead (an unreferenced booking contributes "
        "nothing there; a booking referenced by two items counts twice)."
    )
    total_remaining: float | None = Field(
        default=None,
        description="total_cap - total_spent (USD); null when no cap is set.",
    )
    over_budget: bool = Field(
        description="True if any category with a cap has spent strictly above it."
    )


class TripBudgetSet(AppBaseModel):
    """Request body for POST /trips/{id}/budget. Replace semantics: every POST
    fully replaces the trip's caps — omitted/None categories become uncapped."""

    flights: float | None = Field(default=None, ge=0, description="Flights cap (USD).")
    hotels: float | None = Field(default=None, ge=0, description="Hotels cap (USD).")
    activities: float | None = Field(
        default=None, ge=0, description="Activities cap (USD)."
    )
    buffer: float | None = Field(default=None, ge=0, description="Buffer cap (USD).")
