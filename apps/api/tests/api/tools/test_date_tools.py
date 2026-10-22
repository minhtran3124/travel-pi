from datetime import date, timedelta
from unittest.mock import MagicMock

import app.tools.date_tools as date_tools_module
import pytest
from app.core.config import get_settings
from app.schemas.date_intent import DateIntent
from app.tools.date_tools import resolve_date
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException
from langgraph.types import Command

# Fixed "today" — mirrors tests/core/test_dates.py so tool-level expectations
# cannot drift with the wall clock. A Saturday.
TODAY = date(2026, 7, 11)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    """Pin `resolve_date`'s grounded "today" regardless of the wall clock.

    Patches the name as imported into ``date_tools`` (not the ``app.core.dates``
    original) since that's what the tool actually calls.
    """
    monkeypatch.setattr(date_tools_module, "today_in_timezone", lambda tz_name: TODAY)


class _ScriptedLLM:
    """Fake structured-output LLM: records the messages it received and
    returns one scripted :class:`DateIntent` (or raises, for provider-error
    tests). Mirrors ``_RouterLLM`` in ``tests/agents/test_supervisor_language.py``.
    """

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.received_messages = None

    def with_structured_output(self, *_a, **_k):
        return self

    def invoke(self, messages):
        self.received_messages = messages
        if self._error is not None:
            raise self._error
        return self._response


def _patch_llm(monkeypatch, llm):
    monkeypatch.setattr(date_tools_module, "get_agent_llm", lambda name: llm)


def _no_llm_allowed(monkeypatch):
    """Fail the test loudly if the numeric fast path ever calls the LLM getter."""
    spy = MagicMock(side_effect=AssertionError("get_agent_llm must not be called"))
    monkeypatch.setattr(date_tools_module, "get_agent_llm", spy)
    return spy


def _call(expression: str):
    """Invoke ``resolve_date`` the way ToolNode does.

    The tool takes an ``InjectedToolCallId``, so it must be invoked with a full
    tool-call payload — a bare ``{"expression": ...}`` dict would not supply it.
    """
    return resolve_date.invoke(
        {
            "name": "resolve_date",
            "args": {"expression": expression},
            "id": "tc-test",
            "type": "tool_call",
        }
    )


def _resolve(expression: str) -> str:
    """Return the summary text for an expression that resolves successfully."""
    out = _call(expression)
    assert isinstance(out, ToolMessage), f"expected a resolved date, got {out!r}"
    return out.content


def _blocked(expression: str) -> str:
    """Return the failure text for an expression only the traveller can settle.

    Asserts the gh-109 contract: a resolve failure is reported as a ``Command``
    that sets ``awaiting_user`` (so ``dispatch_next`` abandons the rest of the
    turn's ledger) carrying an ``error``-status ``ToolMessage`` — not a raised
    ``ToolException``, which could not have updated graph state.
    """
    out = _call(expression)
    assert isinstance(out, Command), f"expected a blocked Command, got {out!r}"
    assert out.update["awaiting_user"] is True
    message = out.update["messages"][0]
    assert message.status == "error"
    assert message.tool_call_id == "tc-test"
    return message.content


def test_numeric_iso_expression_resolves_with_zero_llm_calls(monkeypatch):
    spy = _no_llm_allowed(monkeypatch)

    summary = _resolve("2026-07-13")

    assert "2026-07-13" in summary
    spy.assert_not_called()


def test_numeric_day_month_expression_resolves_with_zero_llm_calls(monkeypatch):
    spy = _no_llm_allowed(monkeypatch)

    summary = _resolve("13/07")

    assert "2026-07-13" in summary
    spy.assert_not_called()


def test_word_expression_calls_llm_and_computes_from_intent(monkeypatch):
    # Today is pinned to Sat 2026-07-11. "next monday" -> weekday=0, week="next"
    # -> Monday of next calendar week -> 2026-07-13.
    llm = _ScriptedLLM(response=DateIntent(kind="weekday", weekday=0, week="next"))
    _patch_llm(monkeypatch, llm)

    summary = _resolve("next monday")

    assert "2026-07-13" in summary
    assert llm.received_messages is not None


def test_system_prompt_interpolates_today_weekday_and_zone(monkeypatch):
    llm = _ScriptedLLM(response=DateIntent(kind="relative_day", day_offset=1))
    _patch_llm(monkeypatch, llm)
    tz_name = get_settings().agent_timezone

    _resolve("tomorrow-ish")

    assert llm.received_messages is not None
    system_content = llm.received_messages[0].content
    assert TODAY.isoformat() in system_content
    assert TODAY.strftime("%A") in system_content
    assert tz_name in system_content
    assert "{{TODAY_DATE}}" not in system_content
    assert "{{TODAY_WEEKDAY}}" not in system_content
    assert "{{TIMEZONE}}" not in system_content
    human_content = llm.received_messages[1].content
    assert human_content == "tomorrow-ish"


def test_ambiguous_intent_blocks_on_traveller_with_model_reason(monkeypatch):
    llm = _ScriptedLLM(
        response=DateIntent(kind="ambiguous", reason="no date signal at all")
    )
    _patch_llm(monkeypatch, llm)

    message = _blocked("someday")
    assert "no date signal at all" in message
    assert "ambiguous" in message.lower()
    assert "ask" in message.lower()


def test_bare_month_year_blocks_on_traveller_without_calling_llm(monkeypatch):
    # A bare month/year (no day component) is a numeric-shaped but ambiguous
    # token — parse_numeric_date raises AmbiguousDateError for it, which
    # falls through to the LLM. Script an ambiguous response so the tool's
    # own message still surfaces cleanly.
    llm = _ScriptedLLM(response=DateIntent(kind="ambiguous", reason="no day given"))
    _patch_llm(monkeypatch, llm)

    message = _blocked("07/2026")
    assert "07/2026" in message
    assert "ambiguous" in message.lower()
    assert "ask" in message.lower()


def test_invalid_calendar_date_blocks_on_traveller_without_calling_llm(monkeypatch):
    spy = _no_llm_allowed(monkeypatch)

    message = _blocked("99/99/2026")
    assert "99/99/2026" in message
    assert "not a valid date" in message.lower()
    assert "ask" in message.lower()
    spy.assert_not_called()


def test_past_date_is_rejected():
    # resolve_date must not cheerfully echo back a past date — it's the sole
    # date oracle now, exported over MCP without the search_flights-style
    # past-date guard downstream.
    message = _blocked("2020-07-12")
    assert "2020-07-12" in message
    assert "past" in message.lower()
    assert "ask" in message.lower()


def test_past_date_allows_one_day_grace():
    # Mirrors the 1-day timezone-skew grace in search_flights/search_hotels.
    yesterday = (TODAY - timedelta(days=1)).isoformat()

    summary = _resolve(yesterday)

    assert yesterday in summary


def test_resolved_past_date_from_llm_intent_is_rejected(monkeypatch):
    # The past-date guard applies uniformly after either path resolves an
    # ISO date — exercise it via the LLM path with an explicit past year.
    llm = _ScriptedLLM(response=DateIntent(kind="absolute", year=2020, month=7, day=12))
    _patch_llm(monkeypatch, llm)

    message = _blocked("12 tháng 7 năm 2020")
    assert "2020-07-12" in message
    assert "past" in message.lower()
    assert "ask" in message.lower()


def test_malformed_intent_from_model_blocks_on_traveller_not_crash(monkeypatch):
    # weekday intent missing its `weekday` field — compute_from_intent treats
    # this as malformed input and raises AmbiguousDateError rather than
    # crashing on a None comparison.
    llm = _ScriptedLLM(response=DateIntent(kind="weekday", weekday=None, week="bare"))
    _patch_llm(monkeypatch, llm)

    message = _blocked("some weekday")
    assert "ask" in message.lower()


def test_llm_provider_error_raises_toolexception_not_crash(monkeypatch):
    llm = _ScriptedLLM(error=RuntimeError("provider unavailable"))
    _patch_llm(monkeypatch, llm)

    with pytest.raises(ToolException) as exc_info:
        _call("next friday")

    message = str(exc_info.value)
    assert "next friday" in message
    assert "ask" in message.lower()


def test_falls_back_to_settings_timezone_without_graph_runtime():
    # Outside a graph run (as in this unit test, or a direct/MCP call) there
    # is no runtime to read AgentContext.timezone from, so the tool must fall
    # back to the global setting rather than raise.
    assert date_tools_module._grounding_timezone() == get_settings().agent_timezone


def test_registered_in_planner_concierge_and_booking_domains():
    from app.tools.registry import get_tools_for

    for domain in ("planner", "concierge", "booking"):
        names = {t.name for t in get_tools_for(domain)}
        assert "resolve_date" in names, f"resolve_date missing from {domain}"


def test_metadata_readonly():
    from app.tools.registry import TOOL_METADATA

    assert TOOL_METADATA["resolve_date"] == {"readOnly": True, "destructive": False}
