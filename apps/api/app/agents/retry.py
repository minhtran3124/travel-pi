"""Fault-tolerance policies for the agent graph (specs/agent-fault-tolerance, MIN-49).

Central home for LangGraph retry/error-handling wiring so the graph is the single
retry owner. ``LLM_RETRY`` guards LLM provider calls (rate-limit/network) on every
LLM node; ``TOOL_FAULT`` (retry + narrowed handler + graceful fallback) guards the
real-I/O tool nodes (concierge weather, planner routing). Transient failures are the
provider-agnostic ``UpstreamError`` family; logic failures stay ``ToolException``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException
from langgraph.errors import NodeError
from langgraph.types import Command, RetryPolicy

from app.exceptions import UpstreamError

# Shown to the user after transient retries are exhausted (or a non-retryable
# error surfaces). Mirrors today's tool-unavailable message, minus "do not retry".
GRACEFUL_MSG = (
    "The requested information is temporarily unavailable due to an upstream "
    "problem. Tell the user it could not be retrieved right now and to try again "
    "shortly."
)

# Provider-SDK exception class names that mean "transient" — matched by name so the
# agent layer never imports openai/anthropic (see app/clients/llm.py).
_RETRYABLE_LLM_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "APIConnectionTimeoutError",
}


def _is_retryable_llm(exc: Exception) -> bool:
    """True for transient LLM provider failures; provider-agnostic (no SDK import).

    :param exc: The exception raised by an LLM node.
    :return: Whether the call should be retried.
    """
    code = getattr(exc, "status_code", None)
    if code in (408, 409, 429) or (isinstance(code, int) and 500 <= code < 600):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, ConnectionError)):
        return True
    return exc.__class__.__name__ in _RETRYABLE_LLM_NAMES


# All other RetryPolicy fields keep langgraph defaults (already equal to our params).
LLM_RETRY = RetryPolicy(retry_on=_is_retryable_llm)
TRANSIENT_RETRY = RetryPolicy(retry_on=lambda e: isinstance(e, UpstreamError))


def _tool_error_logic_only(exc: ToolException) -> str:
    """Narrowed ``handle_tool_errors`` for retry sub-agents.

    Annotation ``ToolException`` tells ToolNode to catch only wrapped logic errors;
    a re-raised ``UpstreamError`` is not a ``ToolException`` and propagates to the
    node's ``RetryPolicy``.

    :param exc: The wrapped logic error raised by a tool.
    :return: A message telling the model to self-correct its arguments.
    """
    return (
        f"Tool call failed: {exc}. The request looks invalid — check the arguments "
        "and try a corrected call, or tell the user what is needed."
    )


def graceful_fallback(state: dict, error: NodeError) -> Command:
    """tools-node ``error_handler``: restore graceful degradation after exhaustion.

    The failed ``tools`` node produced no ``ToolMessage`` for any pending call, so a
    provider would reject the next ``assistant`` turn. Emit one ``ToolMessage`` per
    pending ``tool_call_id`` (read from the last ``AIMessage``), then route back to
    ``assistant``.

    :param state: The graph state whose last message is the tool-calling AIMessage.
    :param error: The LangGraph failure context (``error.error`` is the exception).
    :return: A ``Command`` appending graceful tool messages and going to assistant.
    """
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    msgs = [
        ToolMessage(
            content=GRACEFUL_MSG,
            tool_call_id=tc["id"],
            name=tc["name"],
            status="error",
        )
        for tc in tool_calls
    ]
    return Command(goto="assistant", update={"messages": msgs})


@dataclass(frozen=True)
class ToolFaultPolicy:
    """Bundle of the three tool-node fault-tolerance knobs that travel together."""

    retry_policy: RetryPolicy
    handle_tool_errors: Callable
    error_handler: Callable


# Shared bundle for the real-I/O sub-agents (concierge weather, planner routing).
TOOL_FAULT = ToolFaultPolicy(
    retry_policy=TRANSIENT_RETRY,
    handle_tool_errors=_tool_error_logic_only,
    error_handler=graceful_fallback,
)
