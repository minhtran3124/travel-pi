"""Context-aware follow-up suggestion keys, keyed off the agent's current_flow.

Deterministic heuristic (MIN-55 phase 1 -> MIN-65 DESIGN D6 rule engine): each
sub-agent flow maps to a small, curated set of follow-up suggestion *keys*.
Keys are locale-agnostic stable identifiers; the web client resolves them to
localized chip labels/prompts via its i18n catalog (apps/web/messages/*.json ->
Chat.followups). Returns [] for an unknown/None flow so the client renders no
chips.

MIN-65 D6 layers an ordered, specific->generic rule table on top of the
original static per-flow map: when a caller has `trip_facts`/`profile`/
`preferences`, a handful of cross-cutting keys (not namespaced by flow, e.g.
"book_hotel_next") can surface ahead of the flow's own static entries. The
static map (`_FLOW_SUGGESTIONS`) remains the unconditional fallback/floor: a
call with just `current_flow` (the pre-MIN-65 signature) reproduces the old
static-only result exactly for every flow, since none of the rules below can
fire without trip_facts/profile/preferences context.

A future phase may swap this map for LLM-generated suggestions; keep the
`suggestions_for_flow` signature backward compatible (`current_flow`
positional, everything else keyword-only with defaults) so callers (router +
stream mapper) and the response contract do not change.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from app.core.text import fold_diacritics
from app.memory.store import get_profile

logger = logging.getLogger(__name__)

#: Max chips surfaced per turn (keep the UI uncluttered — MIN-55).
MAX_SUGGESTIONS = 3

#: Per-flow catalog. The first three entries of each list are the original
#: MIN-55 static suggestions and MUST stay first/unchanged — the fallback
#: backfill below stops as soon as it has backfilled that many, so a bare
#: `suggestions_for_flow(flow)` call always reproduces them exactly. The
#: entries after that are MIN-65 D6 keys conceptually anchored to that flow;
#: they are never picked by the backfill loop (kept here only so eval's
#: `known_suggestion_keys()`, which flattens this dict, sees the full catalog
#: without needing to change that file).
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

#: Trip starts within this many days -> nudge weather/packing prep (D6 rule 3).
_TRIP_SOON_WINDOW_DAYS = 14

#: Keyword signals (diacritic-folded, lowercase) for the family/budget rules.
_FAMILY_SIGNALS = ("family", "gia dinh", "tre em", "con nho", "kids", "children")
_BUDGET_SIGNALS = ("budget", "ngan sach", "tiet kiem", "gia re", "economical", "cheap")


def _fold(text: str) -> str:
    """Lowercase + diacritic-fold, for locale-insensitive keyword matching.

    :param text: The raw text to normalize.
    :return: The lowercased, diacritic-folded text.
    """
    return fold_diacritics(text.lower())


def _contains_any(text: str, signals: tuple[str, ...]) -> bool:
    """True when any of ``signals`` appears in ``text`` (diacritic-folded).

    :param text: The raw text to search.
    :param signals: Already-folded (lowercase, no diacritics) needles.
    :return: True on the first substring match.
    """
    if not text:
        return False
    folded = _fold(text)
    return any(signal in folded for signal in signals)


def _starts_within_days(start_date: Any, days: int) -> bool:
    """Best-effort: True when ``start_date`` (ISO ``YYYY-MM-DD``) is today or
    within the next ``days`` days.

    Compared against UTC "today" — this function has no per-run timezone
    context (the caller only has trip_facts/profile/preferences, not the
    request's ``AgentContext``), so a traveller whose local date has already
    rolled past midnight UTC may see a one-day skew. Acceptable for a
    suggestion nudge, not a hard deadline.

    :param start_date: The trip_facts ``start_date`` value; anything that
        isn't a parseable ISO date string returns False rather than raising.
    :param days: The lookahead window, in days.
    :return: True when the trip starts within the window and hasn't passed.
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

    MIN-65 D6: an ordered, specific->generic rule table runs first (booking
    handoff, trip-starts-soon, family travel_group, budget signal,
    destination-aware concierge tips); the static per-flow map backfills
    whatever's left, up to the same count it would have returned on its own —
    so a flow's suggestions are never fewer than the pre-D6 static-only
    behavior, and calling with just ``current_flow`` reproduces that behavior
    exactly (none of the rules below can fire on empty/absent context).

    :param current_flow: The sub-agent the supervisor last routed to
        (``planner|concierge|journal|budget|booking``) or ``None``.
    :param trip_facts: The turn's normalized ``trip_facts`` dict (MIN-65 D1),
        or None.
    :param profile: The traveller's personalization dict (MIN-53
        ``get_profile`` shape — ``name``/``gender``/``travel_group`` keys),
        or None.
    :param preferences: The formatted traveller-preferences text block
        (MIN-65 D2), or ``""``.
    :return: A list of stable suggestion keys, or ``[]`` when the flow is
        unknown/``None``.
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

    # Rules 1/2 — booking handoff. A flight-side fact (origin/cabin_class)
    # with no hotel fact yet reads as "just booked the flight" -> nudge
    # toward the hotel; a hotel fact reads as "just booked the hotel" ->
    # nudge toward transport/activities. `suggestions_for_flow` isn't told
    # what tool actually ran this turn, so this is a documented heuristic on
    # the trip_facts available, not a precise "what was just booked" signal.
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

    # Rule 5 — preferences carry a budget-conscious signal. (Deliberately NOT
    # also triggered by `current_flow == "budget"` alone — the budget flow's
    # own static suggestions already cover that ground, and firing on flow
    # alone would make a bare `suggestions_for_flow("budget")` call diverge
    # from its pre-D6 result, breaking the documented backward-compat
    # guarantee above.)
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

    Both call sites (`routers/agent.py`, `streaming/mapper.py`) need the
    traveller's structured profile dict (``get_profile``'s ``{key: text}``
    shape) to feed the `profile` rule above — but ``TravelAgentState.profile``
    only ever carries the pre-formatted *text* block it was built from, not
    the dict. A store miss / no user id / any store error degrades to
    ``None`` (the family rule simply doesn't fire), matching the best-effort
    pattern already used for profile/instructions/preferences elsewhere
    (``nodes.load_context_node``).

    :param store: The graph's long-term store (``graph.store``), or None.
    :param user_id: The effective user id, or None.
    :return: The profile dict, or None on a miss/error/missing input.
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
