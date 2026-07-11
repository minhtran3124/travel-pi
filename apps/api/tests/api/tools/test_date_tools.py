from datetime import timedelta

import pytest
from app.core.config import get_settings
from app.core.dates import today_in_timezone
from app.tools.date_tools import resolve_date
from langchain_core.tools import ToolException


def _today():
    return today_in_timezone(get_settings().agent_timezone)


def test_relative_expression_resolves():
    today = _today()
    expected_iso = (today + timedelta(days=1)).isoformat()

    summary = resolve_date.invoke({"expression": "tomorrow"})

    assert expected_iso in summary


def test_weekday_expression_resolves():
    today = _today()
    delta = (4 - today.weekday()) % 7  # Friday = 4
    if delta == 0:
        delta = 7
    expected = today + timedelta(days=delta)

    summary = resolve_date.invoke({"expression": "next friday"})

    # "next" prefix adds a further 7 days on top of the strictly-future Friday.
    assert (expected + timedelta(days=7)).isoformat() in summary


def test_summary_contains_iso_weekday_and_grounded_today():
    today = _today()
    tz_name = get_settings().agent_timezone
    expected_iso = (today + timedelta(days=1)).isoformat()
    expected_weekday = (today + timedelta(days=1)).strftime("%A")

    summary = resolve_date.invoke({"expression": "tomorrow"})

    assert expected_iso in summary
    assert expected_weekday in summary
    assert today.isoformat() in summary
    assert tz_name in summary


def test_ambiguous_expression_raises_toolexception_telling_agent_to_ask():
    with pytest.raises(ToolException) as exc_info:
        resolve_date.invoke({"expression": "someday"})

    message = str(exc_info.value)
    assert "someday" in message
    assert "ask" in message.lower()


def test_bare_month_year_raises_toolexception():
    with pytest.raises(ToolException):
        resolve_date.invoke({"expression": "07/2026"})


def test_invalid_calendar_date_raises_toolexception():
    with pytest.raises(ToolException):
        resolve_date.invoke({"expression": "99/99/2026"})


def test_registered_in_planner_concierge_and_booking_domains():
    from app.tools.registry import get_tools_for

    for domain in ("planner", "concierge", "booking"):
        names = {t.name for t in get_tools_for(domain)}
        assert "resolve_date" in names, f"resolve_date missing from {domain}"


def test_metadata_readonly():
    from app.tools.registry import TOOL_METADATA

    assert TOOL_METADATA["resolve_date"] == {"readOnly": True, "destructive": False}
