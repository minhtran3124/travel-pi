from datetime import timedelta

import pytest
from app.core.config import get_settings
from app.core.dates import today_in_timezone
from app.tools.flight_tools import search_flights
from langchain_core.tools import ToolException


def test_word_date_is_rejected_toward_resolve_date():
    with pytest.raises(ToolException, match="resolve_date"):
        search_flights.invoke(
            {"origin": "DAD", "destination": "SGN", "departure_date": "ngày mai"}
        )


def test_unparseable_date_raises_toolexception():
    with pytest.raises(ToolException):
        search_flights.invoke(
            {"origin": "DAD", "destination": "SGN", "departure_date": "someday"}
        )


def test_one_day_tz_skew_is_tolerated():
    # A date one day before the server's `today` must NOT be rejected — it may be
    # the traveller's genuine "today" in a timezone behind the server default.
    tool_today = today_in_timezone(get_settings().agent_timezone)
    yesterday = (tool_today - timedelta(days=1)).isoformat()
    summary = search_flights.invoke(
        {"origin": "DAD", "destination": "SGN", "departure_date": yesterday}
    )
    assert isinstance(summary, str) and summary


def test_two_days_past_still_rejected():
    tool_today = today_in_timezone(get_settings().agent_timezone)
    two_days_ago = (tool_today - timedelta(days=2)).isoformat()
    with pytest.raises(ToolException):
        search_flights.invoke(
            {"origin": "DAD", "destination": "SGN", "departure_date": two_days_ago}
        )
