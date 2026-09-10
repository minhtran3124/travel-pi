# tests/agents/test_retry.py
"""Unit tests for the fault-tolerance policies (specs/agent-fault-tolerance, MIN-49)."""

import logging

import httpx
from app.agents.retry import (
    GRACEFUL_MSG,
    LLM_RETRY,
    TRANSIENT_RETRY,
    _is_retryable_llm,
    graceful_fallback,
)
from app.exceptions import NotFoundError, WeatherUnavailableError
from langchain_core.messages import AIMessage
from langgraph.errors import NodeError


def test_is_retryable_llm_status_codes():
    assert _is_retryable_llm(type("E", (Exception,), {"status_code": 429})())
    assert _is_retryable_llm(type("E", (Exception,), {"status_code": 503})())
    assert not _is_retryable_llm(type("E", (Exception,), {"status_code": 400})())


def test_is_retryable_llm_httpx_and_name():
    assert _is_retryable_llm(httpx.ConnectError("boom"))
    assert _is_retryable_llm(type("APITimeoutError", (Exception,), {})())
    assert not _is_retryable_llm(ValueError("nope"))


def test_transient_retry_matches_only_upstream():
    assert TRANSIENT_RETRY.retry_on(WeatherUnavailableError("down"))
    assert not TRANSIENT_RETRY.retry_on(NotFoundError("missing"))


def test_llm_retry_keeps_default_backoff():
    assert LLM_RETRY.max_attempts == 3
    assert LLM_RETRY.retry_on is _is_retryable_llm


def test_graceful_fallback_one_message_per_tool_call():
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_weather", "args": {}, "id": "c1", "type": "tool_call"},
            {"name": "get_route", "args": {}, "id": "c2", "type": "tool_call"},
        ],
    )
    cmd = graceful_fallback(
        {"messages": [ai]}, NodeError(node="tools", error=RuntimeError("x"))
    )
    msgs = cmd.update["messages"]
    assert [m.tool_call_id for m in msgs] == ["c1", "c2"]
    assert all(m.content == GRACEFUL_MSG for m in msgs)
    assert cmd.goto == "assistant"


def test_graceful_fallback_logs_the_exception_with_traceback(caplog):
    """#186: the substituted message is the only other trace, so the real fault
    must reach the logs with its traceback — a deterministic error read as an
    "upstream problem" is what misdiagnosed #178."""
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_weather", "args": {}, "id": "c1", "type": "tool_call"}
        ],
    )
    boom = NotImplementedError("StructuredTool does not support sync invocation.")
    try:
        raise boom
    except NotImplementedError as exc:
        err = NodeError(node="tools", error=exc)

    with caplog.at_level(logging.ERROR, logger="app.agents.retry"):
        graceful_fallback({"messages": [ai]}, err)

    record = next(r for r in caplog.records if r.name == "app.agents.retry")
    assert record.exc_info is not None
    assert record.exc_info[1] is boom
    assert "get_weather" in record.getMessage()
    assert "sync invocation" in caplog.text
