"""Content-level pin for the planner batching-itinerary-writes addition (v12).

Asserts the active planner prompt instructs the model to batch same-turn
``add_itinerary_item`` calls instead of one item per turn, and that the
pre-existing v11 "create the trip first, then add itinerary items in your
next step" guidance survived the bump.
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
