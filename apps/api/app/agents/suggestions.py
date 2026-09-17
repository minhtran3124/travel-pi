"""Context-aware follow-up suggestion keys, keyed off the agent's current_flow.

Each flow maps to a curated set of locale-agnostic suggestion keys the web client
resolves to localized chips; [] for an unknown/None flow. An ordered rule table
(fed by trip_facts/profile/preferences) surfaces cross-cutting keys first, with the
static per-flow map as the floor, so a bare ``current_flow`` call is unchanged.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from app.core.text import fold_diacritics
from app.memory.store import get_profile

logger = logging.getLogger(__name__)

#: Max chips surfaced per turn (keep the UI uncluttered).
MAX_SUGGESTIONS = 3

#: Per-flow catalog. The first three entries of each list MUST stay first/unchanged
#: so a bare ``suggestions_for_flow(flow)`` reproduces them exactly; the rest are
#: cross-cutting keys never picked by the backfill loop.
_FLOW_SUGGESTIONS: dict[str, list[str]] = {
    "planner": [
        "planner.addDay",
        "planner.adjustBudget",
        "planner.findStay",
        "weather_before_trip",
        "packing_tips",
    ],
    "concierge": [
        "concierge.nearbyPlaces",
        "concierge.checkWeather",
        "concierge.getThere",
        "local_tips_destination",
        "family_activities",
    ],
    "journal": ["journal.addNote", "journal.viewTimeline", "journal.tripSummary"],
    "booking": [
        "booking.otherOptions",
        "booking.bookThis",
        "booking.comparePrices",
        "book_hotel_next",
        "transport_to_hotel",
        "activities_near_destination",
    ],
    "budget": [
        "budget.addExpense",
        "budget.remaining",
        "budget.breakdown",
        "budget_check",
    ],
}

#: Trip starts within this many days -> nudge weather/packing prep.
_TRIP_SOON_WINDOW_DAYS = 14

#: Keyword signals (diacritic-folded, lowercase) for the family/budget rules.
_FAMILY_SIGNALS = ("family", "gia dinh", "tre em", "con nho", "kids", "children")
_BUDGET_SIGNALS = ("budget", "ngan sach", "tiet kiem", "gia re", "economical", "cheap")


def _fold(text: str) -> str:
    """Lowercase + diacritic-fold, for locale-insensitive keyword matching."""
    return fold_diacritics(text.lower())


def _contains_any(text: str, signals: tuple[str, ...]) -> bool:
    """True when any of ``signals`` (already folded) appears in ``text``."""
    if not text:
        return False
    folded = _fold(text)
    return any(signal in folded for signal in signals)


def _starts_within_days(start_date: Any, days: int) -> bool:
    """True when ``start_date`` (ISO) is today or within the next ``days`` days.

    Compared against UTC "today" (no per-run timezone here), so a local date past
    midnight UTC may skew by a day — acceptable for a nudge, not a hard deadline.
    Non-parseable input returns False rather than raising.
    """
    if not isinstance(start_date, str) or not start_date:
        return False
    try:
        parsed = date.fromisoformat(start_date)
    except ValueError:
        return False
    today = datetime.now(timezone.utc).date()
    delta = (parsed - today).days
    return 0 <= delta <= days


def suggestions_for_flow(
    current_flow: str | None,
    *,
    trip_facts: dict | None = None,
    profile: dict | None = None,
    preferences: str = "",
) -> list[str]:
    """Return up to MAX_SUGGESTIONS follow-up suggestion keys for a flow.

    An ordered rule table runs first; the static per-flow map backfills the rest, so
    a bare ``current_flow`` call reproduces the static-only behaviour exactly.
    """
    if not current_flow:
        return []

    trip_facts = trip_facts or {}
    profile = profile or {}
    preferences = preferences or ""
    fallback = _FLOW_SUGGESTIONS.get(current_flow, [])

    candidates: list[str] = []

    def _add(*keys: str) -> None:
        for key in keys:
            if key not in candidates:
                candidates.append(key)

    # Rules 1/2 — booking handoff. A heuristic on available trip_facts (the tool that
    # actually ran this turn isn't known): a flight fact with no hotel yet nudges
    # toward the hotel; a hotel fact nudges toward transport/activities.
    has_hotel_fact = bool(trip_facts.get("hotel_area"))
    has_flight_fact = bool(trip_facts.get("origin") or trip_facts.get("cabin_class"))
    if current_flow == "booking" and has_flight_fact and not has_hotel_fact:
        _add("book_hotel_next")
    elif current_flow == "booking" and has_hotel_fact:
        _add("transport_to_hotel", "activities_near_destination")

    # Rule 3 — trip starts soon.
    if _starts_within_days(trip_facts.get("start_date"), _TRIP_SOON_WINDOW_DAYS):
        _add("weather_before_trip", "packing_tips")

    # Rule 4 — travelling with family/kids (free-text travel_group).
    if _contains_any(str(profile.get("travel_group") or ""), _FAMILY_SIGNALS):
        _add("family_activities")

    # Rule 5 — preferences carry a budget-conscious signal. NOT triggered by
    # ``current_flow == "budget"`` alone, which would break the bare-call guarantee.
    if _contains_any(preferences, _BUDGET_SIGNALS):
        _add("budget_check")

    # Rule 6 — concierge flow with a known destination.
    if current_flow == "concierge" and trip_facts.get("destination"):
        _add("local_tips_destination")

    # Fallback floor: never fewer than the static map alone would give.
    floor = min(len(fallback), MAX_SUGGESTIONS)
    for key in fallback:
        if len(candidates) >= floor:
            break
        if key not in candidates:
            candidates.append(key)

    return candidates[:MAX_SUGGESTIONS]


def profile_for_suggestions(store: Any, user_id: str | None) -> dict | None:
    """Best-effort ``get_profile`` fetch for suggestion personalization.

    Callers have only ``TravelAgentState.profile`` (pre-formatted text), not the dict
    the profile rule needs. Any miss/error degrades to ``None`` (the family rule just
    doesn't fire).
    """
    if not store or not user_id:
        return None
    try:
        return get_profile(store, user_id)
    except Exception:  # noqa: BLE001 — best-effort, matches load_context_node
        logger.warning(
            "[suggestions] profile lookup failed for user_id=%s",
            user_id,
            exc_info=True,
        )
        return None
