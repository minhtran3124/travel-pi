"""Content-level pin for the agent-date-resolution prompt rewrite (booking v6 / planner v7).

A prior prompt rewrite in this same feature passed 14/14 tests while silently
dropping a behavioral prohibition; only a live probe caught it. These asserts
pin the actual wording so a future edit can't silently regress it.
"""

import pytest

_ABSENT_PHRASES = [
    "confirmation before you search",
    "get a single yes/no confirmation before you call the tool",
    "to a concrete date yourself",
]


@pytest.mark.parametrize("agent_name", ["booking", "planner"])
def test_active_prompt_mandates_resolve_date_tool(agent_name):
    from app.prompts.registry import registry

    text = registry.get(agent_name)
    assert "resolve_date" in text


@pytest.mark.parametrize("agent_name", ["booking", "planner"])
def test_active_prompt_drops_pre_search_date_confirmation(agent_name):
    from app.prompts.registry import registry

    text = registry.get(agent_name)
    for phrase in _ABSENT_PHRASES:
        assert phrase not in text, f"{agent_name} prompt still contains: {phrase!r}"


def test_booking_prompt_keeps_money_guardrail():
    from app.prompts.registry import registry

    text = registry.get("booking")
    assert "Never confirm a booking without explicit approval" in text
