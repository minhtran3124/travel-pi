"""Fault-tolerance policies for the agent graph, so the graph is the single retry owner.

``LLM_RETRY`` guards LLM provider calls; ``TOOL_FAULT`` guards real-I/O tool nodes.
Transient failures are the ``UpstreamError`` family; logic failures stay ``ToolException``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException
from langgraph.errors import NodeError
from langgraph.prebuilt.tool_node import ToolInvocationError
from langgraph.types import Command, RetryPolicy

from app.exceptions import AppError, UpstreamError

logger = logging.getLogger(__name__)

# Shown after transient retries are exhausted; correct only when the fault was
# upstream, which _fallback_message() gates on.
GRACEFUL_MSG = (
    "The requested information is temporarily unavailable due to an upstream "
    "problem. Tell the user it could not be retrieved right now and to try again "
    "shortly."
)

# Shown when the tools node died of anything else. Says nothing about the exception:
# the same message goes to every pending call, and the exception text belongs in the log.
INTERNAL_FAULT_MSG = (
    "This step did not complete because of a fault in this system, not an upstream "
    "outage. It is NOT temporary and calling the tool again will fail identically — "
    "do not retry it and do not tell the user to try again shortly. Tell the user "
    "plainly that this information could not be retrieved."
)

# Provider-SDK exception class names that mean "transient" — matched by name so the
# agent layer never imports openai/anthropic (see app/clients/llm.py).
_RETRYABLE_LLM_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "APIConnectionTimeoutError",
}


def _is_retryable_llm(exc: Exception) -> bool:
    """True for transient LLM provider failures; provider-agnostic (no SDK import)."""
    code = getattr(exc, "status_code", None)
    if code in (408, 409, 429) or (isinstance(code, int) and 500 <= code < 600):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, ConnectionError)):
        return True
    return exc.__class__.__name__ in _RETRYABLE_LLM_NAMES


# All other RetryPolicy fields keep langgraph defaults (already equal to our params).
LLM_RETRY = RetryPolicy(retry_on=_is_retryable_llm)
TRANSIENT_RETRY = RetryPolicy(retry_on=lambda e: isinstance(e, UpstreamError))


def describe_tool_failure(exc: Exception) -> str:
    """Classify a tool failure and say what recovery it actually has.

    The single source of truth for both ``handle_tool_errors`` hooks. A wrong verdict
    is harmful: "try again shortly" for a deterministic fault loops forever, and "fix
    the arguments" for a missing injected arg asks for something the model cannot supply.
    """
    if isinstance(exc, ToolInvocationError):
        if exc.filtered_errors:
            return (
                f"Tool call failed: {exc}. The arguments are invalid — fix them "
                "and call the tool again, or tell the user what is missing."
            )
        return (
            f"Tool call failed: {exc}. The tool is missing runtime context that "
            "you cannot supply yourself (most often no trip is selected). This is "
            "NOT an outage and retrying will fail identically — ask the traveller "
            "for the missing detail, e.g. which trip they mean."
        )

    # tool_error() is raised as `raise tool_error(e) from e`, so the originating
    # domain error is on __cause__.
    cause = exc.__cause__
    if isinstance(exc, UpstreamError) or isinstance(cause, UpstreamError):
        return (
            f"Tool call failed: {exc}. This is a temporary upstream problem, not a "
            "bad request — do not retry the tool; tell the user the information is "
            "currently unavailable and to try again shortly."
        )
    if isinstance(cause, AppError):
        return (
            f"Tool call failed: {exc}. This is a definite answer about the data, "
            "not an outage — do not tell the user to try again later. Act on the "
            "message above: use the hint if there is one, otherwise tell the user "
            "plainly what was not found or not allowed."
        )
    if isinstance(exc, ToolException):
        return (
            f"Tool call failed: {exc}. That message is the tool's own explanation "
            "of what is wrong, not an outage — do not tell the user to try again "
            "later. If it names a correction you can make yourself (including "
            "calling another tool first), make it and call the tool again; "
            "otherwise tell the user plainly what is needed."
        )
    return (
        f"Tool call failed: {exc}. The cause is unknown — do not claim an outage "
        "and do not retry blindly; tell the user this step did not work and, if "
        "you need something from them to proceed, ask for it."
    )


def _tool_error_logic_only(exc: ToolException) -> str:
    """Narrowed ``handle_tool_errors`` for retry sub-agents: ToolNode catches only
    wrapped logic errors, while a re-raised ``UpstreamError`` reaches the ``RetryPolicy``."""
    return describe_tool_failure(exc)


def _fallback_message(exc: BaseException | None) -> str:
    """Pick the tools-node fallback message that matches the failure.

    ``GRACEFUL_MSG`` (upstream outage, retry) is right only for an ``UpstreamError``;
    a missing/unknown exception takes the non-transient branch, since an outage we
    cannot evidence must not be claimed.
    """
    cause = getattr(exc, "__cause__", None)
    if isinstance(exc, UpstreamError) or isinstance(cause, UpstreamError):
        return GRACEFUL_MSG
    return INTERNAL_FAULT_MSG


def graceful_fallback(state: dict, error: NodeError) -> Command:
    """tools-node ``error_handler``: restore graceful degradation after exhaustion.

    The failed node produced no ``ToolMessage`` for any pending call, so emit one per
    pending ``tool_call_id`` and route back to ``assistant``. The exception is logged
    with its traceback first (the message is all that survives), and _fallback_message
    decides the wording so a deterministic fault is not announced as a transient outage.
    """
    exc = getattr(error, "error", None)
    content = _fallback_message(exc)
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    logger.error(
        "[graceful_fallback] tools node failed; degrading %d pending tool call(s) "
        "%s to %s",
        len(tool_calls),
        [tc["name"] for tc in tool_calls],
        "GRACEFUL_MSG" if content is GRACEFUL_MSG else "INTERNAL_FAULT_MSG",
        exc_info=exc,
    )
    msgs = [
        ToolMessage(
            content=content,
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
