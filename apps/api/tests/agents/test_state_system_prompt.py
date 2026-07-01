"""Task 1.3 — State instructions field + system-prompt fold (specs/agent-memory-layers)."""

from langchain_core.messages import SystemMessage


def test_instructions_field_in_state_schema():
    """TravelAgentState has an 'instructions' annotation."""
    from app.agents.state import TravelAgentState

    assert "instructions" in TravelAgentState.__annotations__


def test_system_with_summary_folds_instructions():
    """Instructions appear in the leading system message."""
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {"instructions": "Always show EUR"}, base
    )
    assert isinstance(combined, SystemMessage)
    assert "BASE" in combined.content
    assert "Standing traveller instructions" in combined.content
    assert "Always show EUR" in combined.content


def test_system_with_summary_instructions_before_summary():
    """Instructions are folded BEFORE the summary (per D4)."""
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
    """All three (instructions, trip_context, summary) are folded together."""
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
    """Empty instructions still return base unchanged when trip_context/summary also empty."""
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    result = system_with_summary({"instructions": ""}, base)
    assert result is base


def test_new_user_no_behavior_change():
    """All-empty fields → base prompt unchanged (no behavior change for new users)."""
    from app.agents.state import system_with_summary

    base = SystemMessage(content="BASE")
    result = system_with_summary({}, base)
    assert result is base
