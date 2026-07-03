"""Place tools tests (specs/travel-agent Task 3.2; args_schema Task 2.3)."""

import json

import pytest
from app.tools.place_tools import (
    ListPlaceCategoriesArgs,
    NearbyPlacesArgs,
    ParseNlQueryArgs,
    ResolvePlaceArgs,
    SearchPlacesArgs,
    list_place_categories,
    nearby_places,
    parse_nl_query,
    resolve_place,
    search_places,
)
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException
from pydantic import ValidationError


def _call(tool, args: dict) -> ToolMessage:
    """Invoke a content_and_artifact tool via a ToolCall, returning the ToolMessage.

    A bare-dict ``.invoke({...})`` on a content_and_artifact tool silently drops
    the artifact and returns only the content string, so business behaviour must
    be asserted through the ``ToolMessage`` a proper ToolCall yields.
    """
    return tool.invoke(
        {"type": "tool_call", "id": "t1", "name": tool.name, "args": args}
    )


def test_all_place_tools_have_args_schema():
    assert search_places.args_schema is SearchPlacesArgs
    assert nearby_places.args_schema is NearbyPlacesArgs
    assert resolve_place.args_schema is ResolvePlaceArgs
    assert parse_nl_query.args_schema is ParseNlQueryArgs
    assert list_place_categories.args_schema is ListPlaceCategoriesArgs


def test_search_places_price_level_invalid_raises_on_invoke():
    with pytest.raises(ValidationError):
        search_places.invoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": "search_places",
                "args": {"price_level": 7},
            }
        )


def test_search_places_min_rating_bounds_in_schema():
    schema = search_places.get_input_schema().model_json_schema()
    min_rating_schema = schema["properties"]["min_rating"]["anyOf"][0]
    assert min_rating_schema.get("minimum") == 0
    assert min_rating_schema.get("maximum") == 5


def test_search_places_price_level_bounds_in_schema():
    schema = search_places.get_input_schema().model_json_schema()
    price_level_schema = schema["properties"]["price_level"]["anyOf"][0]
    assert price_level_schema.get("minimum") == 1
    assert price_level_schema.get("maximum") == 4


def test_resolve_place_schema_lists_source_enum_values():
    schema_json = json.dumps(resolve_place.get_input_schema().model_json_schema())
    assert "catalog" in schema_json
    assert "saved" in schema_json


def test_list_place_categories_schema_has_no_properties():
    schema = list_place_categories.get_input_schema().model_json_schema()
    assert schema.get("properties", {}) == {}


def test_search_places_returns_list_for_seeded_city(agent_db):
    from app.tools.place_tools import search_places

    msg = _call(search_places, {"city": "Tokyo"})
    assert isinstance(msg.artifact["data"]["places"], list)
    assert len(msg.artifact["data"]["places"]) > 0


def test_search_places_matching_search_emits_places_panel(agent_db):
    from app.tools.place_tools import search_places

    msg = _call(search_places, {"city": "Tokyo"})
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and msg.content.strip()
    assert msg.artifact["kind"] == "places"


def test_search_places_unknown_city_returns_empty(agent_db):
    from app.tools.place_tools import search_places

    msg = _call(search_places, {"city": "Nowhereville"})
    assert msg.artifact is None


def test_search_places_no_args_returns_list(agent_db):
    from app.tools.place_tools import search_places

    msg = _call(search_places, {})
    assert isinstance(msg.artifact["data"]["places"], list)
    assert len(msg.artifact["data"]["places"]) > 0


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


def test_search_places_exclude_names_omits_matches(agent_db):
    from app.tools.place_tools import search_places

    baseline = _call(search_places, {"city": "Tokyo"}).artifact["data"]["places"]
    assert len(baseline) == 4

    excluded = [baseline[0]["name"], baseline[1]["name"]]
    filtered = _call(
        search_places, {"city": "Tokyo", "exclude_names": excluded}
    ).artifact["data"]["places"]

    assert len(filtered) == len(baseline) - 2
    assert not set(excluded) & {p["name"] for p in filtered}
