"""Fault-tolerance policies for the agent graph (specs/agent-fault-tolerance, MIN-49).

Central home for LangGraph retry/error-handling wiring so the graph is the single
retry owner. ``LLM_RETRY`` guards LLM provider calls (rate-limit/network) on every
LLM node; ``TOOL_FAULT`` (retry + narrowed handler + graceful fallback) guards the
real-I/O tool nodes (concierge weather, planner routing). Transient failures are the
provider-agnostic ``UpstreamError`` family; logic failures stay ``ToolException``.
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

# Shown after transient retries are exhausted. Mirrors today's tool-unavailable
# message, minus "do not retry". Only correct when the fault really was upstream:
# the node's TRANSIENT_RETRY only retries UpstreamError, so exhaustion is exactly
# the UpstreamError case and _fallback_message() gates on it (#186).
GRACEFUL_MSG = (
    "The requested information is temporarily unavailable due to an upstream "
    "problem. Tell the user it could not be retrieved right now and to try again "
    "shortly."
)

# Shown when the tools node died of anything else (#186). Deliberately says nothing
# about the exception: at this level the failure belongs to the node, not to any one
# tool -- the same message goes to every pending call, healthy siblings included --
# and the exception text is an internal string, so it belongs in the log that
# graceful_fallback writes, not in the model's context.
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


def describe_tool_failure(exc: Exception) -> str:
    """Classify a tool failure and say what recovery it actually has (#113).

    The single source of truth for both ``handle_tool_errors`` hooks, so a
    failure reads the same whether the sub-agent was built with a
    ``ToolFaultPolicy`` or not. Each hook still *catches* a different set (that
    is what its annotation decides); only the wording lives here.

    Every branch exists because a wrong verdict is actively harmful: telling the
    traveller to "try again shortly" for a deterministic failure sends them into
    a loop that can never succeed, and telling the model to "fix the arguments"
    for a missing injected arg asks for something it cannot supply.

    * ``ToolInvocationError`` with model-fixable errors → correct the arguments.
    * ``ToolInvocationError`` with none → the only unmet requirements are
      ``InjectedState``/``InjectedStore`` args, which the model cannot supply, so
      langgraph filters them out and leaves an empty error list. A runtime
      precondition is missing (typically no active trip); ask the traveller.
    * ``UpstreamError`` (raised bare, or as the cause) → genuinely transient.
      Bare matters: weather/routing/climate tools re-raise ``UpstreamError``
      untouched so the node's ``RetryPolicy`` sees it, and the catch-all hook is
      the backstop for every tool error — so it must not read as unknown there.
    * any other ``AppError`` cause → a deterministic domain error whose message
      already carries ``detail`` + ``hint`` from :func:`app.tools._base.tool_error`.
    * a causeless ``ToolException`` → a validation message the tool wrote itself
      (``raise ToolException(...)`` with no ``from``, e.g. date/flight/hotel arg
      checks). It is a logic error the model can often act on — several name the
      exact correction — so it must not be filed under "cause unknown".

    :param exc: The exception raised by a tool call.
    :return: A user-safe message describing the failure and its recovery.
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

    # tool_error() is always raised as `raise tool_error(e) from e`, so the
    # originating domain error is on __cause__ (app/tools/_base.py).
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
    """Narrowed ``handle_tool_errors`` for retry sub-agents.

    Annotation ``ToolException`` tells ToolNode to catch only wrapped logic errors;
    a re-raised ``UpstreamError`` is not a ``ToolException`` and propagates to the
    node's ``RetryPolicy``.

    The catch set stays narrow, but the wording is shared with the default hook
    (#113): planner and concierge take this path and both bind injected-state
    trip tools, so "check the arguments and try a corrected call" was telling the
    model to fix something it cannot reach.

    :param exc: The wrapped logic error raised by a tool.
    :return: A message describing the failure and the recovery it actually has.
    """
    return describe_tool_failure(exc)


def _fallback_message(exc: BaseException | None) -> str:
    """Pick the tools-node fallback message that matches the failure (#186).

    ``GRACEFUL_MSG`` asserts an upstream outage and tells the model to send the
    traveller back to retry. That is right for exactly one failure: the node's
    ``TRANSIENT_RETRY`` retries ``UpstreamError`` and nothing else, so an exhausted
    retry *is* an ``UpstreamError``. For a ``NotImplementedError``, a ``TypeError``
    or any other deterministic fault, both halves of the claim are false and the
    retry it invites can never succeed.

    A missing/unknown exception takes the non-transient branch on purpose: claiming
    an outage we cannot evidence is the failure mode this fixes.

    :param exc: The exception that killed the tools node, if the runtime gave one.
    :return: ``GRACEFUL_MSG`` for a genuine upstream fault, else ``INTERNAL_FAULT_MSG``.
    """
    cause = getattr(exc, "__cause__", None)
    if isinstance(exc, UpstreamError) or isinstance(cause, UpstreamError):
        return GRACEFUL_MSG
    return INTERNAL_FAULT_MSG


def graceful_fallback(state: dict, error: NodeError) -> Command:
    """tools-node ``error_handler``: restore graceful degradation after exhaustion.

    The failed ``tools`` node produced no ``ToolMessage`` for any pending call, so a
    provider would reject the next ``assistant`` turn. Emit one ``ToolMessage`` per
    pending ``tool_call_id`` (read from the last ``AIMessage``), then route back to
    ``assistant``.

    Two things about that substitution are load-bearing (#186). The message is the
    only thing that survives this handler, so the exception is logged with its
    traceback first -- without it a deterministic fault leaves no trace anywhere.
    And which message is sent is decided by :func:`_fallback_message`, so such a
    fault is not announced to the traveller as a transient outage. Both halves come
    from #178, where a ``NotImplementedError`` presented only as "upstream problem"
    and was diagnosed wrong.

    :param state: The graph state whose last message is the tool-calling AIMessage.
    :param error: The LangGraph failure context (``error.error`` is the exception).
    :return: A ``Command`` appending graceful tool messages and going to assistant.
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
