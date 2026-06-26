"""Place tools tests (specs/travel-agent Task 3.2)."""

import pytest
from langchain_core.tools import ToolException


def test_search_places_returns_list_for_seeded_city(agent_db):
    from app.tools.place_tools import search_places

    out = search_places.invoke({"city": "Tokyo"})
    assert isinstance(out, list)


def test_search_places_unknown_city_returns_empty(agent_db):
    from app.tools.place_tools import search_places

    out = search_places.invoke({"city": "Nowhereville"})
    assert out == []


def test_search_places_no_args_returns_list(agent_db):
    from app.tools.place_tools import search_places

    out = search_places.invoke({})
    assert isinstance(out, list)


def test_list_place_categories_non_empty(agent_db):
    from app.tools.place_tools import list_place_categories

    out = list_place_categories.invoke({})
    assert isinstance(out, list)
    assert len(out) > 0
    # Each entry has name, color, icon
    assert "name" in out[0]


def test_parse_nl_query_returns_dict(agent_db):
    from app.tools.place_tools import parse_nl_query

    out = parse_nl_query.invoke({"query": "cheap food in Tokyo"})
    assert isinstance(out, dict)
    assert "city" in out
    assert "category" in out


def test_parse_nl_query_extracts_category(agent_db):
    from app.tools.place_tools import parse_nl_query

    out = parse_nl_query.invoke({"query": "cheap food in Tokyo"})
    assert out["category"] == "restaurant"


def test_resolve_place_returns_none_for_unknown(agent_db):
    from app.tools.place_tools import resolve_place

    out = resolve_place.invoke({"place_id": "nonexistent-id-xyz"})
    assert out is None


def test_nearby_places_raises_for_unknown_origin(agent_db):
    from app.tools.place_tools import nearby_places

    with pytest.raises(ToolException):
        nearby_places.invoke({"place_id": "nonexistent-id-xyz"})
