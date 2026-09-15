"""Content-level pin for the planner prompt (v12 batching, v13 search-first).

Asserts the active planner prompt instructs the model to batch same-turn
``add_itinerary_item`` calls instead of one item per turn, that the
pre-existing v11 "create the trip first, then add itinerary items in your
next step" guidance survived the bump, and that v13 tells the model a bare
search never opens a trip.
"""

from app.prompts.registry import registry


def test_planner_prompt_batches_itinerary_writes():
    text = registry.get("planner")
    assert "add_itinerary_item" in text
    assert "same response" in text


def test_planner_prompt_keeps_create_trip_first_step():
    text = registry.get("planner")
    normalized = " ".join(text.split())
    assert (
        "create the trip first, then add itinerary items in your next step"
        in normalized
    )


def test_planner_prompt_searches_before_creating_a_trip():
    text = registry.get("planner")
    normalized = " ".join(text.split())
    assert "Never call `create_trip` before a search" in normalized
    assert "Search first, save later" in normalized


def test_planner_prompt_asks_when_no_date_given():
    """gh-191: a no-date search must ask, not fall back to today."""
    normalized = " ".join(registry.get("planner").split())
    assert "No date given → ask, never search." in normalized
    assert "never use today's date" in normalized
    assert "needs_clarification" in normalized


def test_planner_v16_honours_a_known_budget():
    """gh-152: a budget in Known trip facts sizes the plan and is reported against."""
    normalized = " ".join(registry.get("planner", version=16).split())
    assert "## Plan to a known budget" in normalized
    assert "lists a `budget`" in normalized
    assert "size hotel, food, and activity choices to it" in normalized
    assert "estimated total (or per-day) spend against that budget" in normalized
    assert "never ask for the budget again" in normalized
    assert "No `budget` in Known trip facts → plan as usual" in normalized
