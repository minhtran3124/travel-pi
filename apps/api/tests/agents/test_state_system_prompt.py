"""State instructions field + system-prompt fold."""

from langchain_core.messages import SystemMessage


def test_instructions_field_in_state_schema():
    from app.agents.state import TravelAgentState

    assert "instructions" in TravelAgentState.__annotations__


def test_system_with_summary_folds_instructions():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary({"instructions": "Always show EUR"}, base)
    assert isinstance(combined, SystemMessage)
    assert "BASE" in combined.content
    assert "Standing traveller instructions" in combined.content
    assert "Always show EUR" in combined.content


def test_system_with_summary_instructions_before_summary():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {
            "instructions": "Always show EUR",
            "summary": "traveller is vegetarian",
        },
        base,
    )
    content = combined.content
    instr_idx = content.index("Standing traveller instructions")
    summary_idx = content.index("Summary of earlier conversation")
    assert instr_idx < summary_idx, "instructions must come before summary"


def test_system_with_summary_all_three_fields():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {
            "instructions": "Show EUR",
            "trip_context": "Active trip: Rome",
            "summary": "vegetarian",
        },
        base,
    )
    assert "BASE" in combined.content
    assert "Standing traveller instructions" in combined.content
    assert "Show EUR" in combined.content
    assert "Current trip context" in combined.content
    assert "Rome" in combined.content
    assert "Summary of earlier conversation" in combined.content
    assert "vegetarian" in combined.content


def test_system_with_summary_empty_instructions_unchanged():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    result = system_with_summary({"instructions": ""}, base)
    assert result is base


def test_new_user_no_behavior_change():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    result = system_with_summary({}, base)
    assert result is base


def test_profile_field_in_state_schema():
    from app.agents.state import TravelAgentState

    assert "profile" in TravelAgentState.__annotations__


def test_system_with_summary_folds_profile():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary({"profile": "- Name: Minh"}, base)
    assert "Traveller profile:" in combined.content
    assert "- Name: Minh" in combined.content
    assert "BASE" in combined.content


def test_system_with_summary_profile_before_instructions():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {"profile": "- Name: Minh", "instructions": "Always show EUR"}, base
    )
    c = combined.content
    assert c.index("Traveller profile:") < c.index("Standing traveller instructions")


def test_system_with_summary_empty_profile_unchanged():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    assert system_with_summary({"profile": ""}, base) is base


def test_account_email_field_in_state_schema():
    from app.agents.state import TravelAgentState

    assert "account_email" in TravelAgentState.__annotations__


def test_system_with_summary_folds_account_email():
    """The signed-in account email must reach the system message so the model can offer it for booking."""
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary({"account_email": "traveller@example.com"}, base)
    assert "Signed-in account email:" in combined.content
    assert "traveller@example.com" in combined.content
    assert "BASE" in combined.content


def test_system_with_summary_account_email_after_profile():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {"profile": "- Name: Minh", "account_email": "minh@example.com"}, base
    )
    c = combined.content
    assert c.index("Traveller profile:") < c.index("Signed-in account email:")


def test_system_with_summary_no_account_email_unchanged():
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    assert system_with_summary({"account_email": None}, base) is base


def test_trip_context_label_says_one_trip_not_a_list():
    """The shared trip-context label must scope itself to the one open trip, not the traveller's full trip list."""
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary({"trip_context": "Active trip: Rome"}, base)
    content = combined.content
    assert "Current trip context" in content
    assert "is not a list of the traveller's trips" in content


def test_trip_context_label_names_no_tool():
    """The label reaches sub-agents like concierge that bind no trip tools, so naming one would promise a capability it lacks."""
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary({"trip_context": "Active trip: Rome"}, base)
    label = combined.content.split("Current trip context", 1)[1].split(":\n", 1)[0]
    for tool_name in (
        "list_trips",
        "get_trip",
        "create_trip",
        "update_trip",
        "search_trips",
    ):
        assert tool_name not in label
