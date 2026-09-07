"""Task 6.1 — suggestion rule engine (MIN-65 DESIGN D6)."""

from datetime import datetime, timedelta, timezone

import pytest
from app.agents.suggestions import (
    _FLOW_SUGGESTIONS,
    MAX_SUGGESTIONS,
    profile_for_suggestions,
    suggestions_for_flow,
)


def _iso(days_from_now: int) -> str:
    return (
        datetime.now(timezone.utc).date() + timedelta(days=days_from_now)
    ).isoformat()


def _catalog() -> set:
    return {key for keys in _FLOW_SUGGESTIONS.values() for key in keys}


# --- backward compatibility -------------------------------------------------


def test_bare_call_matches_old_static_behavior_for_every_flow():
    """Calling with only current_flow (no kwargs) reproduces the pre-D6 static
    map exactly, for every flow — none of the new rules can fire on empty
    context, so the floor backfill alone determines the result."""
    expected = {
        "planner": ["planner.addDay", "planner.adjustBudget", "planner.findStay"],
        "concierge": [
            "concierge.nearbyPlaces",
            "concierge.checkWeather",
            "concierge.getThere",
        ],
        "journal": ["journal.addNote", "journal.viewTimeline", "journal.tripSummary"],
        "booking": [
            "booking.otherOptions",
            "booking.bookThis",
            "booking.comparePrices",
        ],
        "budget": ["budget.addExpense", "budget.remaining", "budget.breakdown"],
    }
    for flow, keys in expected.items():
        assert suggestions_for_flow(flow) == keys


def test_bare_call_also_matches_with_explicit_empty_kwargs():
    assert suggestions_for_flow(
        "planner", trip_facts=None, profile=None, preferences=""
    ) == suggestions_for_flow("planner")
    assert suggestions_for_flow(
        "planner", trip_facts={}, profile={}, preferences=""
    ) == suggestions_for_flow("planner")


def test_none_and_unknown_flow_return_empty():
    assert suggestions_for_flow(None) == []
    assert suggestions_for_flow("") == []
    assert suggestions_for_flow("unknown") == []
    assert suggestions_for_flow("supervisor") == []


# --- rules 1/2: booking handoff ---------------------------------------------


def test_booking_flight_booked_no_hotel_suggests_book_hotel_next():
    keys = suggestions_for_flow(
        "booking", trip_facts={"origin": "HAN", "cabin_class": "economy"}
    )
    assert keys[0] == "book_hotel_next"
    assert len(keys) <= MAX_SUGGESTIONS


def test_booking_hotel_booked_suggests_transport_and_activities():
    keys = suggestions_for_flow("booking", trip_facts={"hotel_area": "District 1"})
    assert keys[:2] == ["transport_to_hotel", "activities_near_destination"]


def test_booking_hotel_and_flight_facts_present_treated_as_hotel_booked():
    """hotel_area already present -> rule 2 wins (never suggest hotel again)."""
    keys = suggestions_for_flow(
        "booking", trip_facts={"origin": "HAN", "hotel_area": "District 1"}
    )
    assert "book_hotel_next" not in keys
    assert keys[:2] == ["transport_to_hotel", "activities_near_destination"]


def test_booking_no_facts_falls_back_to_static_map():
    assert (
        suggestions_for_flow("booking", trip_facts={})
        == _FLOW_SUGGESTIONS["booking"][:3]
    )


def test_flight_fact_outside_booking_flow_does_not_trigger_handoff_rule():
    keys = suggestions_for_flow("planner", trip_facts={"origin": "HAN"})
    assert "book_hotel_next" not in keys


# --- rule 3: trip starts soon ------------------------------------------------


def test_trip_starting_soon_suggests_weather_and_packing():
    keys = suggestions_for_flow("planner", trip_facts={"start_date": _iso(5)})
    assert "weather_before_trip" in keys
    assert "packing_tips" in keys


def test_trip_starting_today_counts_as_soon():
    keys = suggestions_for_flow("planner", trip_facts={"start_date": _iso(0)})
    assert "weather_before_trip" in keys


def test_trip_far_in_future_does_not_trigger_weather_rule():
    keys = suggestions_for_flow("planner", trip_facts={"start_date": _iso(30)})
    assert "weather_before_trip" not in keys
    assert "packing_tips" not in keys


def test_trip_start_date_in_past_does_not_trigger_weather_rule():
    keys = suggestions_for_flow("planner", trip_facts={"start_date": _iso(-1)})
    assert "weather_before_trip" not in keys


def test_malformed_start_date_is_ignored_not_raised():
    keys = suggestions_for_flow("planner", trip_facts={"start_date": "next friday"})
    assert "weather_before_trip" not in keys
    assert keys  # still falls back cleanly, no crash


def test_non_string_start_date_is_ignored_not_raised():
    keys = suggestions_for_flow("planner", trip_facts={"start_date": 12345})
    assert "weather_before_trip" not in keys


# --- rule 4: family travel group --------------------------------------------


def test_family_travel_group_suggests_family_activities():
    keys = suggestions_for_flow(
        "concierge", profile={"travel_group": "family with young children"}
    )
    assert "family_activities" in keys


def test_solo_travel_group_does_not_trigger_family_rule():
    keys = suggestions_for_flow("concierge", profile={"travel_group": "solo"})
    assert "family_activities" not in keys


def test_missing_travel_group_key_does_not_trigger_family_rule():
    keys = suggestions_for_flow("concierge", profile={"name": "Minh"})
    assert "family_activities" not in keys


# --- rule 5: budget signal in preferences -----------------------------------


def test_budget_signal_in_preferences_suggests_budget_check():
    keys = suggestions_for_flow(
        "concierge", preferences="- budget_band: tiet kiem, gia re options only"
    )
    assert "budget_check" in keys


def test_vietnamese_diacritics_budget_signal_is_folded_and_matched():
    keys = suggestions_for_flow("concierge", preferences="- budget_band: tiết kiệm")
    assert "budget_check" in keys


def test_no_budget_signal_does_not_trigger_budget_rule():
    keys = suggestions_for_flow("concierge", preferences="- diet: vegetarian")
    assert "budget_check" not in keys


def test_budget_flow_alone_does_not_force_budget_check():
    """Deliberate deviation from a literal 'flow=budget always triggers' reading
    of DESIGN D6 — see suggestions.py rule 5 docstring: firing on flow alone
    would break the bare-call backward-compat guarantee for the budget flow."""
    assert suggestions_for_flow("budget") == _FLOW_SUGGESTIONS["budget"][:3]


# --- rule 6: concierge + known destination ----------------------------------


def test_concierge_with_destination_suggests_local_tips():
    keys = suggestions_for_flow("concierge", trip_facts={"destination": "Hoi An"})
    assert "local_tips_destination" in keys


def test_destination_without_concierge_flow_does_not_trigger_local_tips():
    keys = suggestions_for_flow("planner", trip_facts={"destination": "Hoi An"})
    assert "local_tips_destination" not in keys


# --- MAX cap + catalog membership -------------------------------------------


def test_max_three_cap_enforced_even_with_multiple_rule_matches():
    keys = suggestions_for_flow(
        "concierge",
        trip_facts={"destination": "Hoi An", "start_date": _iso(2)},
        profile={"travel_group": "family with kids"},
        preferences="- budget_band: tiet kiem",
    )
    assert len(keys) == MAX_SUGGESTIONS


@pytest.mark.parametrize(
    "flow,trip_facts,profile,preferences",
    [
        ("booking", {"origin": "HAN"}, None, ""),
        ("booking", {"hotel_area": "D1"}, None, ""),
        ("planner", {"start_date": None}, None, ""),
        ("planner", {"start_date": "2026-08-01"}, None, ""),
        ("concierge", None, {"travel_group": "family"}, ""),
        ("concierge", None, None, "tiet kiem"),
        ("concierge", {"destination": "Hue"}, None, ""),
        ("journal", None, None, ""),
        (None, None, None, ""),
    ],
)
def test_every_returned_key_is_in_the_catalog(flow, trip_facts, profile, preferences):
    keys = suggestions_for_flow(
        flow, trip_facts=trip_facts, profile=profile, preferences=preferences
    )
    catalog = _catalog()
    assert all(k in catalog for k in keys)


def test_result_never_shorter_than_old_static_map_for_any_flow():
    """Acceptance-criterion floor: rule-driven results are never shorter than
    the pre-D6 static map would have given for that flow."""
    for flow in ("planner", "concierge", "journal", "booking", "budget"):
        old_len = len(_FLOW_SUGGESTIONS.get(flow, [])[:3])
        # A context that fires exactly one rule for most flows.
        keys = suggestions_for_flow(flow, trip_facts={"start_date": _iso(1)})
        assert len(keys) >= old_len


# --- profile_for_suggestions helper -----------------------------------------


def test_profile_for_suggestions_returns_none_without_store_or_user():
    assert profile_for_suggestions(None, "u1") is None
    assert profile_for_suggestions(object(), None) is None


def test_profile_for_suggestions_reads_profile_dict():
    from app.memory.store import get_store, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u_sugg", "travel_group", {"text": "family with kids"})

    profile = profile_for_suggestions(store, "u_sugg")
    assert profile == {"travel_group": "family with kids"}


def test_profile_for_suggestions_swallows_store_errors():
    class BoomStore:
        def get(self, *args, **kwargs):
            raise RuntimeError("store unavailable")

    assert profile_for_suggestions(BoomStore(), "u1") is None
