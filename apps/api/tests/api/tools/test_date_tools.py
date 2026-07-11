from datetime import date, timedelta

import app.tools.date_tools as date_tools_module
import pytest
from app.core.config import get_settings
from app.tools.date_tools import resolve_date
from langchain_core.tools import ToolException

# Fixed "today" — mirrors tests/core/test_dates.py so tool-level expectations
# cannot drift with the wall clock. A Thursday.
TODAY = date(2026, 7, 9)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    """Pin `resolve_date`'s grounded "today" regardless of the wall clock.

    Patches the name as imported into ``date_tools`` (not the ``app.core.dates``
    original) since that's what the tool actually calls.
    """
    monkeypatch.setattr(date_tools_module, "today_in_timezone", lambda tz_name: TODAY)


def test_relative_expression_resolves():
    expected_iso = (TODAY + timedelta(days=1)).isoformat()

    summary = resolve_date.invoke({"expression": "tomorrow"})

    assert expected_iso in summary


def test_weekday_expression_resolves():
    delta = (4 - TODAY.weekday()) % 7  # Friday = 4
    if delta == 0:
        delta = 7
    expected = TODAY + timedelta(days=delta)

    summary = resolve_date.invoke({"expression": "next friday"})

    # "next" prefix adds a further 7 days on top of the strictly-future Friday.
    assert (expected + timedelta(days=7)).isoformat() in summary


def test_summary_contains_iso_weekday_and_grounded_today():
    tz_name = get_settings().agent_timezone
    resolved = TODAY + timedelta(days=1)

    summary = resolve_date.invoke({"expression": "tomorrow"})

    assert resolved.isoformat() in summary
    assert resolved.strftime("%A") in summary
    assert TODAY.isoformat() in summary
    assert tz_name in summary


def test_summary_spells_out_month_so_it_cannot_be_misread():
    # Finding 4: an ISO-only echo lets a day-first misreading survive
    # unchallenged. The summary must spell the month out.
    resolved = TODAY + timedelta(days=1)

    summary = resolve_date.invoke({"expression": "tomorrow"})

    assert resolved.strftime("%B") in summary  # full month name, not "07"/"04"
    assert str(resolved.day) in summary
    assert resolved.strftime("%A") in summary


def test_ambiguous_expression_raises_toolexception_telling_agent_to_ask():
    with pytest.raises(ToolException) as exc_info:
        resolve_date.invoke({"expression": "someday"})

    message = str(exc_info.value)
    assert "someday" in message
    assert "ambiguous" in message.lower()
    assert "ask" in message.lower()


def test_bare_month_year_raises_toolexception():
    # A bare month/year (no day component) is ambiguous, not an invalid
    # calendar date — resolve_travel_date raises AmbiguousDateError for it.
    with pytest.raises(ToolException) as exc_info:
        resolve_date.invoke({"expression": "07/2026"})

    message = str(exc_info.value)
    assert "07/2026" in message
    assert "ambiguous" in message.lower()
    assert "ask" in message.lower()


def test_invalid_calendar_date_raises_toolexception():
    with pytest.raises(ToolException) as exc_info:
        resolve_date.invoke({"expression": "99/99/2026"})

    message = str(exc_info.value)
    assert "99/99/2026" in message
    assert "not a valid date" in message.lower()
    assert "ask" in message.lower()


def test_past_date_is_rejected():
    # Finding 2: resolve_date must not cheerfully echo back a past date —
    # it's the sole date oracle now, exported over MCP without the
    # search_flights-style past-date guard downstream.
    with pytest.raises(ToolException) as exc_info:
        resolve_date.invoke({"expression": "2020-07-12"})

    message = str(exc_info.value)
    assert "2020-07-12" in message
    assert "past" in message.lower()
    assert "ask" in message.lower()


def test_past_date_allows_one_day_grace():
    # Mirrors the 1-day timezone-skew grace in search_flights/search_hotels.
    yesterday = (TODAY - timedelta(days=1)).isoformat()

    summary = resolve_date.invoke({"expression": yesterday})

    assert yesterday in summary


def test_overflow_from_resolver_converts_to_toolexception(monkeypatch):
    # Finding 3: resolve_date is the public boundary — no bug in the resolver
    # (bounded day-offsets or not) should ever escape as a raw OverflowError.
    # Exercised directly against the tool's own except clause, independent of
    # whatever guard app.core.dates puts around day-offsets internally.
    def _raise_overflow(raw, today):
        raise OverflowError("date value out of range")

    monkeypatch.setattr(date_tools_module, "resolve_travel_date", _raise_overflow)

    with pytest.raises(ToolException) as exc_info:
        resolve_date.invoke({"expression": "in 99999999999999999999999999 days"})

    message = str(exc_info.value)
    assert "not a valid date" in message.lower()
    assert "ask" in message.lower()


def test_falls_back_to_settings_timezone_without_graph_runtime():
    # Finding 1: outside a graph run (as in this unit test, or a direct/MCP
    # call) there is no runtime to read AgentContext.timezone from, so the
    # tool must fall back to the global setting rather than raise.
    assert date_tools_module._grounding_timezone() == get_settings().agent_timezone


def test_registered_in_planner_concierge_and_booking_domains():
    from app.tools.registry import get_tools_for

    for domain in ("planner", "concierge", "booking"):
        names = {t.name for t in get_tools_for(domain)}
        assert "resolve_date" in names, f"resolve_date missing from {domain}"


def test_metadata_readonly():
    from app.tools.registry import TOOL_METADATA

    assert TOOL_METADATA["resolve_date"] == {"readOnly": True, "destructive": False}
