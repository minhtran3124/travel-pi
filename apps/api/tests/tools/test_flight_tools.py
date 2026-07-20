"""Tests for search_flights' args_schema (specs/standardize-tool-args-schema Task 1.1)."""

import json

import pytest
from app.tools.flight_tools import SearchFlightsArgs, search_flights
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

SORT_VALUES = [
    "departure_asc",
    "departure_desc",
    "price_asc",
    "price_desc",
    "duration_asc",
    "duration_desc",
]


def test_search_flights_has_args_schema():
    assert search_flights.args_schema is SearchFlightsArgs
    assert search_flights.args_schema is not None


def test_search_flights_schema_lists_all_sort_values():
    schema_json = json.dumps(search_flights.get_input_schema().model_json_schema())
    for value in SORT_VALUES:
        assert value in schema_json


def test_search_flights_valid_invoke_returns_content_and_artifact(agent_db):
    msg = search_flights.invoke(
        {
            "type": "tool_call",
            "id": "t1",
            "name": "search_flights",
            "args": {
                "origin": "HAN",
                "destination": "SGN",
                "departure_date": "2027-03-15",
            },
        }
    )
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and msg.content.strip()
    assert msg.artifact["kind"] == "flights"


def test_search_flights_invalid_sort_raises_validation_error(agent_db):
    with pytest.raises(ValidationError):
        search_flights.invoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": "search_flights",
                "args": {
                    "origin": "HAN",
                    "destination": "SGN",
                    "departure_date": "2027-03-15",
                    "sort": "cheapest",
                },
            }
        )


def test_search_flights_return_date_is_optional_and_defaults_none():
    assert SearchFlightsArgs.model_fields["return_date"].default is None
    assert SearchFlightsArgs.model_fields["return_date"].is_required() is False


def test_search_flights_omitting_return_date_is_one_way(agent_db):
    """MIN-67 regression: omitting `return_date` must leave one-way behavior
    byte-identical — no return leg searched, summary says "one-way"."""
    msg = search_flights.invoke(
        {
            "type": "tool_call",
            "id": "t1",
            "name": "search_flights",
            "args": {
                "origin": "HAN",
                "destination": "SGN",
                "departure_date": "2027-03-15",
            },
        }
    )
    assert "one-way" in msg.content
    assert "return" not in msg.content.lower()


def test_search_flights_with_return_date_searches_the_return_leg(agent_db):
    """MIN-67: passing `return_date` must search the return leg for real fares
    instead of the model deriving a round-trip total by doubling the outbound."""
    msg = search_flights.invoke(
        {
            "type": "tool_call",
            "id": "t1",
            "name": "search_flights",
            "args": {
                "origin": "HAN",
                "destination": "SGN",
                "departure_date": "2027-03-15",
                "return_date": "2027-03-22",
            },
        }
    )
    assert "return flights" in msg.content
    assert "outbound" in msg.content
    assert "SGN→HAN" in msg.content
    # The panel still reflects the outbound leg only; the return leg's real
    # fare is surfaced in the text the model reads.
    assert msg.artifact["kind"] == "flights"
    assert msg.artifact["data"]["origin"] == "HAN"
