"""Tests for preference-aware re-ranking (MIN-65 task 6.2, DESIGN.md D7).

Two layers: pure unit tests of ``rank_by_preference`` against synthetic items,
and tool-level tests proving the wiring into ``search_hotels``/``browse_hotels``
(``app/tools/hotel_tools.py``) and ``search_flights`` (``app/tools/flight_tools.py``)
— injection stays hidden from the model's schema, matching hotels/flights bubble
to the top, ties keep their original order, and results are deterministic.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.tools._ranking import rank_by_preference
from app.tools.flight_tools import SearchFlightsArgs, search_flights
from app.tools.hotel_tools import (
    BrowseHotelsArgs,
    SearchHotelsArgs,
    browse_hotels,
    search_hotels,
)

# --- rank_by_preference: pure unit tests -----------------------------------


@dataclass
class Item:
    name: str
    tag: str


def _tag_keyword_fn(item: Item) -> list[tuple[list[str], str]]:
    return [([item.tag], item.tag)]


def test_rank_by_preference_boosts_matching_item_to_top():
    items = [Item("budget", "budget"), Item("luxury", "luxury"), Item("mid", "mid")]
    ranked, reasons = rank_by_preference(
        items, "I really want a luxury stay", keyword_fn=_tag_keyword_fn
    )
    assert ranked[0].name == "luxury"
    # non-matches keep their original relative order
    assert [i.name for i in ranked[1:]] == ["budget", "mid"]
    assert reasons == ["luxury"]


def test_rank_by_preference_empty_preferences_is_noop():
    items = [Item("a", "x"), Item("b", "y")]
    ranked, reasons = rank_by_preference(items, "", keyword_fn=_tag_keyword_fn)
    assert ranked is items
    assert reasons == []

    ranked2, reasons2 = rank_by_preference(items, "   ", keyword_fn=_tag_keyword_fn)
    assert ranked2 is items
    assert reasons2 == []


def test_rank_by_preference_ties_keep_original_order():
    """Stability proof: two items with the equal (nonzero) score preserve order."""
    items = [Item("first", "spa"), Item("second", "spa")]
    ranked, reasons = rank_by_preference(
        items, "loves a spa", keyword_fn=_tag_keyword_fn
    )
    assert [i.name for i in ranked] == ["first", "second"]
    assert reasons == ["spa"]


def test_rank_by_preference_never_drops_items():
    items = [Item("a", "x"), Item("b", "y"), Item("c", "z")]
    ranked, reasons = rank_by_preference(
        items, "no match at all here", keyword_fn=_tag_keyword_fn
    )
    assert len(ranked) == len(items)
    assert {i.name for i in ranked} == {i.name for i in items}
    assert reasons == []


def test_rank_by_preference_folds_diacritics_both_sides():
    items = [Item("far", "other"), Item("beachfront", "biển")]
    ranked, reasons = rank_by_preference(
        items,
        "Tôi thích khách sạn gần biển",
        keyword_fn=lambda i: [([i.tag], "beachfront")],
    )
    assert ranked[0].name == "beachfront"
    assert reasons == ["beachfront"]


def test_rank_by_preference_dedupes_reasons_first_seen_order():
    items = [Item("a", "spa"), Item("b", "spa"), Item("c", "pool")]
    ranked, reasons = rank_by_preference(
        items, "wants a spa and a pool please", keyword_fn=_tag_keyword_fn
    )
    assert reasons == ["spa", "pool"]  # deduped, first-seen order
    assert len(ranked) == 3


def test_rank_by_preference_does_not_false_match_short_keyword_inside_a_word():
    """Regression: a short keyword like the 2-letter airline code "ke" must not
    match as a substring of ordinary words like "likes"/"weekend"/"tickets"."""
    items = [Item("first", "ke"), Item("second", "other")]
    ranked, reasons = rank_by_preference(
        items, "Traveller likes booking tickets early", keyword_fn=_tag_keyword_fn
    )
    assert [i.name for i in ranked] == ["first", "second"]  # unchanged order
    assert reasons == []


def test_rank_by_preference_does_not_false_match_word_inside_a_longer_token():
    """Regression: "hotel" must not match inside the store key "hotel_type" —
    the preferences block folds `- {key}: {text}` lines, so the key text is
    part of the haystack (see nodes.py load_context_node)."""
    items = [Item("first", "hotel"), Item("second", "other")]
    ranked, reasons = rank_by_preference(
        items,
        "- hotel_type: Traveller prefers boutique stays",
        keyword_fn=_tag_keyword_fn,
    )
    assert [i.name for i in ranked] == ["first", "second"]  # unchanged order
    assert reasons == []


def test_rank_by_preference_real_word_boundary_match_still_works():
    """A genuine, standalone mention of a short-ish keyword still matches."""
    items = [Item("first", "spa"), Item("second", "other")]
    ranked, reasons = rank_by_preference(
        items, "Traveller wants a spa", keyword_fn=_tag_keyword_fn
    )
    assert ranked[0].name == "first"
    assert reasons == ["spa"]


# --- Tool wiring: injection stays hidden from the model-facing schema ------


def _facing(tool):
    """Model-facing schema fields (matches the convention in test_memory_tools.py)."""
    return tool.tool_call_schema.model_fields


def test_search_hotels_preferences_hidden_from_schema():
    fields = _facing(search_hotels)
    assert "preferences" not in fields
    # `preferences` is declared on SearchHotelsArgs (not just the function
    # signature) so LangGraph's ToolNode treats it as optional when a caller's
    # state lacks the key (e.g. a bare subgraph invoke, or a future MCP-exposed
    # call that never went through load_context_node) — see MIN-65 task 6.2
    # follow-up fix. It must still be excluded from the model-facing schema.
    assert set(fields) == set(SearchHotelsArgs.model_fields) - {"preferences"}
    assert "preferences" not in search_hotels.args


def test_browse_hotels_preferences_hidden_from_schema():
    fields = _facing(browse_hotels)
    assert "preferences" not in fields
    assert set(fields) == set(BrowseHotelsArgs.model_fields) - {"preferences"}
    assert "preferences" not in browse_hotels.args


def test_search_flights_preferences_hidden_from_schema():
    fields = _facing(search_flights)
    assert "preferences" not in fields
    assert set(fields) == set(SearchFlightsArgs.model_fields) - {"preferences"}
    assert "preferences" not in search_flights.args


def test_browse_hotels_tolerates_state_without_preferences_key():
    """Regression guard: a caller whose state lacks `preferences` entirely
    (e.g. a subgraph test or an MCP-exposed call bypassing load_context_node)
    must not KeyError — the field's schema default makes it optional at the
    LangGraph ToolNode injection layer, not just at the Python call layer.
    """
    from app.agents.subagents._base import build_subagent
    from app.clients.llm import FakeLLM
    from app.prompts.registry import registry
    from app.tools.registry import get_tools_for
    from langchain_core.messages import AIMessage, HumanMessage

    fake = FakeLLM(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "browse_hotels",
                        "args": {"city": "Da Nang"},
                        "id": "h1",
                    }
                ],
            ),
            "Here are some hotels.",
        ]
    )
    subgraph = build_subagent(
        "concierge_no_prefs_test",
        get_tools_for("concierge"),
        lambda _: fake,
        registry.get("concierge"),
    )
    result = subgraph.invoke(
        {"messages": [HumanMessage(content="find me a hotel in Da Nang")]}
    )
    tool_msgs = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert any(m.name == "browse_hotels" for m in tool_msgs)


def test_preferences_param_present_on_function_for_injection():
    """The Annotated[..., InjectedState] param must stay on the underlying
    function so LangGraph's ToolNode can inject it — only the model-facing
    schema hides it (mirrors test_memory_tools.py's equivalent check).
    """
    for t in (search_hotels, browse_hotels, search_flights):
        params = inspect.signature(t.func).parameters
        assert "preferences" in params, t.name
        assert params["preferences"].default == "", t.name


# --- Functional: matching results are boosted, boost-only, deterministic --


def test_browse_hotels_prioritizes_star_preference(agent_db):
    baseline = browse_hotels.func(city="Da Nang")
    boosted = browse_hotels.func(
        city="Da Nang", preferences="Traveller wants a 5-star stay for this trip."
    )
    baseline_hotels = baseline[1]["data"]["hotels"]
    boosted_hotels = boosted[1]["data"]["hotels"]

    # Boost-only: same set of hotels, never filtered.
    assert {h["id"] for h in baseline_hotels} == {h["id"] for h in boosted_hotels}
    assert any(h["star_rating"] == 5 for h in boosted_hotels), (
        "fixture needs a 5-star hotel"
    )
    assert any(h["star_rating"] != 5 for h in boosted_hotels), (
        "fixture needs a non-5-star one"
    )

    # 5-star hotels are grouped at the front.
    seen_non_five = False
    for h in boosted_hotels:
        if h["star_rating"] == 5:
            assert not seen_non_five, "a 5-star hotel appeared after a non-5-star one"
        else:
            seen_non_five = True

    # Stable: within each score group, the baseline (cheapest-first) order is kept.
    baseline_five = [h["id"] for h in baseline_hotels if h["star_rating"] == 5]
    boosted_five = [h["id"] for h in boosted_hotels if h["star_rating"] == 5]
    assert boosted_five == baseline_five

    baseline_rest = [h["id"] for h in baseline_hotels if h["star_rating"] != 5]
    boosted_rest = [h["id"] for h in boosted_hotels if h["star_rating"] != 5]
    assert boosted_rest == baseline_rest

    assert "Prioritized based on your preferences" in boosted[0]
    assert "5-star" in boosted[0]
    assert "Prioritized" not in baseline[0]


def test_browse_hotels_preference_ranking_is_deterministic(agent_db):
    prefs = "Traveller wants a 5-star stay for this trip."
    first = browse_hotels.func(city="Da Nang", preferences=prefs)
    second = browse_hotels.func(city="Da Nang", preferences=prefs)
    ids1 = [h["id"] for h in first[1]["data"]["hotels"]]
    ids2 = [h["id"] for h in second[1]["data"]["hotels"]]
    assert ids1 == ids2
    assert first[0] == second[0]


def test_search_hotels_wires_preferences_into_summary(agent_db):
    check_in = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
    check_out = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    kwargs = {
        "city": "Da Nang",
        "check_in": check_in,
        "check_out": check_out,
        "rooms": 1,
        "adults": 2,
        "children": 0,
    }
    baseline = search_hotels.func(**kwargs)
    boosted = search_hotels.func(
        **kwargs, preferences="Traveller wants a 5-star stay for this trip."
    )
    baseline_hotels = baseline[1]["data"]["hotels"]
    boosted_hotels = boosted[1]["data"]["hotels"]

    assert {h["id"] for h in baseline_hotels} == {h["id"] for h in boosted_hotels}
    assert any(h["star_rating"] == 5 for h in boosted_hotels), (
        "fixture needs a 5-star hotel"
    )
    assert boosted_hotels[0]["star_rating"] == 5
    assert "Prioritized based on your preferences" in boosted[0]
    assert "Prioritized" not in baseline[0]


def test_search_flights_prioritizes_time_of_day_preference(agent_db):
    departure = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
    kwargs = {"origin": "HAN", "destination": "SGN", "departure_date": departure}
    baseline = search_flights.func(**kwargs)
    boosted = search_flights.func(
        **kwargs, preferences="Traveller prefers evening flights"
    )

    baseline_flights = baseline[1]["data"]["flights"]
    boosted_flights = boosted[1]["data"]["flights"]

    def is_evening(flight: dict) -> bool:
        return datetime.fromisoformat(flight["departure_time"]).hour >= 18

    assert {f["id"] for f in baseline_flights} == {f["id"] for f in boosted_flights}
    assert any(is_evening(f) for f in boosted_flights), (
        "fixture needs an evening flight"
    )
    assert any(not is_evening(f) for f in boosted_flights), (
        "fixture needs a non-evening flight"
    )

    seen_non_evening = False
    for f in boosted_flights:
        if is_evening(f):
            assert not seen_non_evening, (
                "an evening flight appeared after a non-evening one"
            )
        else:
            seen_non_evening = True

    baseline_evening = [f["id"] for f in baseline_flights if is_evening(f)]
    boosted_evening = [f["id"] for f in boosted_flights if is_evening(f)]
    assert boosted_evening == baseline_evening

    baseline_rest = [f["id"] for f in baseline_flights if not is_evening(f)]
    boosted_rest = [f["id"] for f in boosted_flights if not is_evening(f)]
    assert boosted_rest == baseline_rest

    assert "Prioritized based on your preferences" in boosted[0]
    assert "evening" in boosted[0].lower()
    assert "Prioritized" not in baseline[0]


def test_search_flights_preference_ranking_is_deterministic(agent_db):
    departure = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
    kwargs = {"origin": "HAN", "destination": "SGN", "departure_date": departure}
    prefs = "Traveller prefers evening flights"
    first = search_flights.func(**kwargs, preferences=prefs)
    second = search_flights.func(**kwargs, preferences=prefs)
    ids1 = [f["id"] for f in first[1]["data"]["flights"]]
    ids2 = [f["id"] for f in second[1]["data"]["flights"]]
    assert ids1 == ids2


# --- Regression: preferences (learned memory / PII) must never reach logs --


def test_search_hotels_does_not_log_preferences(agent_db, caplog):
    """ce-code-review finding: log_tool_call(..., locals()) was emitting the
    traveller's full learned-preferences block (diet, health, budget, etc.)
    at INFO on every search — a new PII surface introduced alongside the
    `preferences` param. It must be redacted, not just present-but-fine."""
    import logging

    with caplog.at_level(logging.INFO, logger="app.tools"):
        check_in = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        check_out = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
        search_hotels.func(
            city="Da Nang",
            check_in=check_in,
            check_out=check_out,
            rooms=1,
            adults=2,
            children=0,
            preferences="- diet: traveller has a severe shellfish allergy",
        )
    logged = "\n".join(r.message for r in caplog.records)
    assert "shellfish" not in logged
    assert "<redacted>" in logged


def test_search_flights_does_not_log_preferences(agent_db, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="app.tools"):
        departure = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        search_flights.func(
            origin="HAN",
            destination="SGN",
            departure_date=departure,
            preferences="- diet: traveller has a severe shellfish allergy",
        )
    logged = "\n".join(r.message for r in caplog.records)
    assert "shellfish" not in logged
    assert "<redacted>" in logged
