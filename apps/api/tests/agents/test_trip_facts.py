"""Task 3.1 — trip_facts reducer + preferences/pending_flows state foundation (MIN-65 DESIGN D1/D2)."""

from langchain_core.messages import SystemMessage

# ---------------------------------------------------------------------------
# merge_trip_facts reducer
# ---------------------------------------------------------------------------


def test_merge_trip_facts_new_non_none_overlays_old():
    from app.agents.state import merge_trip_facts

    old = {"destination": "Hanoi", "adults": 2}
    new = {"destination": "Da Nang"}
    assert merge_trip_facts(old, new) == {"destination": "Da Nang", "adults": 2}


def test_merge_trip_facts_none_value_does_not_delete():
    from app.agents.state import merge_trip_facts

    old = {"destination": "Da Nang", "adults": 2}
    new = {"destination": None, "adults": 3}
    # None in the update means "no info this turn" -> old key survives untouched.
    assert merge_trip_facts(old, new) == {"destination": "Da Nang", "adults": 3}


def test_merge_trip_facts_old_none_starts_empty():
    from app.agents.state import merge_trip_facts

    assert merge_trip_facts(None, {"destination": "Hue"}) == {"destination": "Hue"}


def test_merge_trip_facts_old_empty_dict():
    from app.agents.state import merge_trip_facts

    assert merge_trip_facts({}, {"destination": "Hue"}) == {"destination": "Hue"}


def test_merge_trip_facts_new_none_keeps_old_unchanged():
    from app.agents.state import merge_trip_facts

    old = {"destination": "Hue"}
    assert merge_trip_facts(old, None) == {"destination": "Hue"}
    assert merge_trip_facts(old, {}) == {"destination": "Hue"}


def test_merge_trip_facts_sequential_turns_preserve_unrelated_keys():
    from app.agents.state import merge_trip_facts

    # Turn 1: destination + party size.
    state = merge_trip_facts(None, {"destination": "Da Nang", "adults": 2})
    # Turn 2: dates added, destination not mentioned again (None).
    state = merge_trip_facts(
        state,
        {"destination": None, "start_date": "2026-08-15", "end_date": "2026-08-20"},
    )
    # Turn 3: party size updated, everything else untouched.
    state = merge_trip_facts(state, {"adults": 3, "children": 1})

    assert state == {
        "destination": "Da Nang",
        "adults": 3,
        "start_date": "2026-08-15",
        "end_date": "2026-08-20",
        "children": 1,
    }


# ---------------------------------------------------------------------------
# TravelAgentState schema
# ---------------------------------------------------------------------------


def test_trip_facts_field_in_state_schema():
    from app.agents.state import TravelAgentState

    assert "trip_facts" in TravelAgentState.__annotations__


def test_preferences_field_in_state_schema():
    from app.agents.state import TravelAgentState

    assert "preferences" in TravelAgentState.__annotations__


def test_pending_flows_field_in_state_schema():
    from app.agents.state import TravelAgentState

    assert "pending_flows" in TravelAgentState.__annotations__


# ---------------------------------------------------------------------------
# system_with_summary folding
# ---------------------------------------------------------------------------


def test_system_with_summary_folds_trip_facts_bullets():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {"trip_facts": {"destination": "Da Nang", "adults": 2}}, base
    )
    content = combined.content
    assert "Known trip facts" in content
    assert "do NOT ask again" in content
    assert "- destination: Da Nang" in content
    assert "- adults: 2" in content


def test_system_with_summary_trip_facts_skips_falsy_values():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {"trip_facts": {"destination": "Da Nang", "children": 0, "hotel_area": ""}},
        base,
    )
    content = combined.content
    assert "- destination: Da Nang" in content
    assert "children" not in content
    assert "hotel_area" not in content


def test_system_with_summary_folds_preferences():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {"preferences": "- diet: vegetarian\n- hotel_type: beachfront"}, base
    )
    content = combined.content
    assert "Traveller preferences" in content
    assert "learned from past conversations" in content
    assert "- diet: vegetarian" in content


def test_system_with_summary_trip_facts_and_preferences_order():
    """trip_facts then preferences, both AFTER the four pre-existing fields."""
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {
            "profile": "- Name: Minh",
            "instructions": "Always show EUR",
            "trip_context": "Active trip: Rome",
            "summary": "traveller is vegetarian",
            "trip_facts": {"destination": "Da Nang"},
            "preferences": "- diet: vegetarian",
        },
        base,
    )
    c = combined.content
    profile_idx = c.index("Traveller profile:")
    instr_idx = c.index("Standing traveller instructions")
    trip_ctx_idx = c.index("Current trip context")
    summary_idx = c.index("Summary of earlier conversation")
    facts_idx = c.index("Known trip facts")
    prefs_idx = c.index("Traveller preferences")

    assert profile_idx < instr_idx < trip_ctx_idx < summary_idx < facts_idx < prefs_idx


def test_system_with_summary_empty_trip_facts_unchanged():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    assert system_with_summary({"trip_facts": {}}, base) is base
    assert system_with_summary({"trip_facts": None}, base) is base


def test_system_with_summary_empty_preferences_unchanged():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    assert system_with_summary({"preferences": ""}, base) is base


def test_system_with_summary_full_empty_state_identity():
    """All six foldable fields empty/absent -> base returned unchanged (no behavior
    change for new users/turns), matching the existing identity-case convention."""
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    assert system_with_summary({}, base) is base
    assert (
        system_with_summary(
            {
                "profile": "",
                "instructions": "",
                "trip_context": "",
                "summary": "",
                "trip_facts": {},
                "preferences": "",
            },
            base,
        )
        is base
    )
