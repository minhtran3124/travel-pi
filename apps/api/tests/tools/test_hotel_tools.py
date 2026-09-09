"""Tests for hotel tools' args_schema (specs/standardize-tool-args-schema Task 2.1)."""

import json

import pytest
from app.tools.hotel_tools import (
    BookHotelArgs,
    BrowseHotelsArgs,
    SearchHotelsArgs,
    book_hotel,
    browse_hotels,
    search_hotels,
)
from langchain_core.messages import ToolMessage
from pydantic import ValidationError


def test_browse_hotels_has_args_schema():
    assert browse_hotels.args_schema is BrowseHotelsArgs
    assert browse_hotels.args_schema is not None


def test_browse_hotels_required_fields():
    schema = BrowseHotelsArgs.model_json_schema()
    required = set(schema.get("required", []))
    assert required == {"city"}


def test_browse_hotels_optional_fields_default_none():
    fields = BrowseHotelsArgs.model_fields
    assert fields["min_stars"].default is None
    assert fields["max_price"].default is None
    assert fields["amenities"].default is None


def test_browse_hotels_valid_invoke_returns_content_and_artifact(agent_db):
    msg = browse_hotels.invoke(
        {
            "type": "tool_call",
            "id": "t1",
            "name": "browse_hotels",
            "args": {"city": "Da Nang"},
        }
    )
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and msg.content.strip()
    assert msg.artifact["kind"] == "hotels"
    data = msg.artifact["data"]
    assert data["results_count"] >= 1
    assert data["check_in"] == "" and data["check_out"] == "" and data["nights"] == 0


def test_browse_hotels_sorted_cheapest_first(agent_db):
    msg = browse_hotels.invoke(
        {
            "type": "tool_call",
            "id": "t1",
            "name": "browse_hotels",
            "args": {"city": "Da Nang"},
        }
    )
    hotels = msg.artifact["data"]["hotels"]
    prices = [h["price_per_night"] for h in hotels]
    assert prices == sorted(prices), "panel must lead with the cheapest hotel"


def test_browse_hotels_unknown_city_returns_no_match_and_no_artifact(agent_db):
    msg = browse_hotels.invoke(
        {
            "type": "tool_call",
            "id": "t1",
            "name": "browse_hotels",
            "args": {"city": "Nowheresville"},
        }
    )
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and msg.content.strip()
    assert msg.artifact is None


def test_search_hotels_has_args_schema():
    assert search_hotels.args_schema is SearchHotelsArgs
    assert search_hotels.args_schema is not None


def test_book_hotel_has_args_schema():
    assert book_hotel.args_schema is BookHotelArgs
    assert book_hotel.args_schema is not None


def test_search_hotels_required_fields():
    schema = SearchHotelsArgs.model_json_schema()
    required = set(schema.get("required", []))
    assert required == {"city", "check_in", "check_out", "rooms", "adults", "children"}


def test_search_hotels_optional_fields_default_none():
    fields = SearchHotelsArgs.model_fields
    assert fields["min_stars"].default is None
    assert fields["max_price"].default is None
    assert fields["amenities"].default is None


def test_search_hotels_min_stars_bounds():
    schema_json = json.dumps(SearchHotelsArgs.model_json_schema())
    schema = SearchHotelsArgs.model_json_schema()
    # min_stars is Optional[int], so bounds live in the anyOf/int branch
    min_stars_schema = schema["properties"]["min_stars"]
    assert "1" in schema_json  # sanity: bound values are serialized somewhere
    # locate the int branch (direct or via anyOf) and check ge/le
    int_branch = min_stars_schema
    if "anyOf" in min_stars_schema:
        int_branch = next(
            b for b in min_stars_schema["anyOf"] if b.get("type") == "integer"
        )
    assert int_branch["minimum"] == 1
    assert int_branch["maximum"] == 5


def test_book_hotel_required_fields():
    schema = BookHotelArgs.model_json_schema()
    required = set(schema.get("required", []))
    assert required == {
        "hotel_id",
        "check_in",
        "check_out",
        "guest_name",
        "guest_email",
        "guest_phone",
    }


def test_book_hotel_defaults():
    fields = BookHotelArgs.model_fields
    assert fields["rooms"].default == 1
    assert fields["adults"].default == 2
    assert fields["children"].default == 0
    assert fields["notes"].default is None
    assert fields["confirm"].default is False


def test_book_hotel_confirm_description_mentions_must_be_true():
    description = BookHotelArgs.model_fields["confirm"].description
    assert "true" in description.lower()


def test_search_hotels_valid_invoke_returns_content_and_artifact(agent_db):
    msg = search_hotels.invoke(
        {
            "type": "tool_call",
            "id": "t1",
            "name": "search_hotels",
            "args": {
                "city": "Da Nang",
                "check_in": "2027-03-15",
                "check_out": "2027-03-18",
                "rooms": 1,
                "adults": 2,
                "children": 0,
            },
        }
    )
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and msg.content.strip()
    assert msg.artifact["kind"] == "hotels"


def test_search_hotels_invalid_rooms_type_raises_validation_error(agent_db):
    with pytest.raises(ValidationError):
        search_hotels.invoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": "search_hotels",
                "args": {
                    "city": "Da Nang",
                    "check_in": "2027-03-15",
                    "check_out": "2027-03-18",
                    "rooms": "not-a-number",
                    "adults": 2,
                    "children": 0,
                },
            }
        )


def test_browse_hotels_description_points_at_search_hotels():
    description = " ".join(browse_hotels.description.split())
    assert "no dates" in description
    assert "search_hotels" in description
    assert "As soon as they give check-in and check-out" in description
    assert "for a real reservation with exact dates" not in description


def test_search_hotels_description_reuses_what_the_traveller_gave():
    """The dated tool must not send the model back to re-ask for known values.

    This description is read by the planner and booking agents as well as the
    concierge, so it carries two rules at once: never invent a value the traveller
    did not give (the anti-hallucination guard, kept verbatim in spirit), and reuse
    what they already said instead of demanding confirmation (#147 — the concierge
    now answers dated hotel questions, and an extra round-trip there is the cost).
    """
    description = " ".join(search_hotels.description.split())
    assert "never guess or assume a value the traveller has not given" in description
    assert "search with them instead of asking again" in description
    assert "restate them and ask the traveller to confirm" not in description
