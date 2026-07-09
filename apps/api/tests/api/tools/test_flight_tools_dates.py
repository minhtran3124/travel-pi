import pytest
from app.tools.flight_tools import search_flights
from langchain_core.tools import ToolException


def test_relative_date_resolves_and_searches():
    summary = search_flights.invoke(
        {"origin": "DAD", "destination": "SGN", "departure_date": "ngày mai"}
    )
    assert isinstance(summary, str) and summary


def test_unparseable_date_raises_toolexception():
    with pytest.raises(ToolException):
        search_flights.invoke(
            {"origin": "DAD", "destination": "SGN", "departure_date": "someday"}
        )
