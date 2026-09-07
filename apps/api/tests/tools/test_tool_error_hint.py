"""Tests for the tool-error hint propagation fix (specs/tool-error-hint-propagation).

``AppError.__str__`` returns ``detail`` only, so the old ``ToolException(str(e))``
call sites silently dropped ``hint`` — a recovery pointer written specifically for
the agent to self-correct. ``app.tools._base.tool_error`` folds ``detail`` and
``hint`` into one model-visible message; these tests cover the helper directly and
one real end-to-end path through an actual tool.
"""

import asyncio

import pytest
from app.exceptions import AppError, CityNotFoundError
from app.tools._base import tool_error
from langchain_core.tools import ToolException


def test_tool_error_with_hint_includes_both_detail_and_hint():
    e = CityNotFoundError(
        "Could not find a location named 'Nowhereville'", hint="Check the spelling."
    )
    result = tool_error(e)
    assert isinstance(result, ToolException)
    assert "Could not find a location named 'Nowhereville'" in str(result)
    assert "Check the spelling." in str(result)


def test_tool_error_without_hint_matches_str_exactly():
    e = CityNotFoundError("Could not find a location named 'Nowhereville'")
    result = tool_error(e)
    assert str(result) == str(e)
    assert not str(result).endswith((":", "-", "None"))
    assert "None" not in str(result)


def test_tool_error_preserves_cause_chain():
    original = CityNotFoundError("not found", hint="try again")
    caught = None
    try:
        try:
            raise original
        except AppError as e:
            raise tool_error(e) from e
    except ToolException as exc:
        caught = exc
    assert caught is not None
    assert caught.__cause__ is original


def test_get_weather_tool_surfaces_hint_to_model(monkeypatch):
    """End-to-end: a real tool's AppError->ToolException path carries the hint."""
    from app.tools import weather_tools

    async def boom(*a, **k):
        raise CityNotFoundError(
            "Could not find a location named 'Xyzzy'",
            hint="Check the spelling, or use GET /cities?q=<partial-name> to find a supported city name.",
        )

    monkeypatch.setattr(weather_tools.weather_service, "get_weather", boom)

    with pytest.raises(ToolException) as exc_info:
        asyncio.run(weather_tools.get_weather.ainvoke({"city": "Xyzzy"}))

    message = str(exc_info.value)
    assert "Could not find a location named 'Xyzzy'" in message
    assert "GET /cities?q=<partial-name>" in message
