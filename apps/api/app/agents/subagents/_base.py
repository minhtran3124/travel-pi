"""Sub-agent factory (specs/travel-agent Task 5.1).

A specialist sub-agent is a small ReAct subgraph: an ``assistant`` node binds the
domain's tools and answers; if it emits tool calls, ``ToolNode`` runs them
(catching ``ToolException`` -> ``ToolMessage(status="error")`` so the model can
self-correct) and control returns to the assistant; otherwise the loop ends.

Compiled subgraphs are added as nodes to the supervisor graph (Task 5.4); the
parent's checkpointer and store propagate into these nested nodes at runtime, so
tools using ``InjectedStore`` work without per-sub-agent wiring.

C.1 (specs/runtime-context-config): ``build_subagent`` accepts a
``resolve_model`` callable instead of a fixed ``llm``. The ``assistant`` node
resolves + binds the model via ``resolve_model(None)`` — the per-request model
hint was removed in MIN-43; model selection now comes from the DB/env-backed
``get_agent_llm`` config.
"""

from __future__ import annotations

import logging
import typing
from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode, tools_condition
from langgraph.runtime import Runtime
from langgraph.types import Command

from app.agents.constants import EPISODIC_TOOL_NAME, NO_ACTIVE_TRIP_MSG
from app.agents.context import AgentContext
from app.agents.retry import LLM_RETRY, ToolFaultPolicy, describe_tool_failure
from app.agents.state import (
    TravelAgentState,
    ground_current_date,
    system_with_summary,
    with_reply_language,
)
from app.prompts.registry import registry
from app.tools.clarification_tools import needs_clarification

logger = logging.getLogger(__name__)


def _tool_error_to_message(exc: Exception) -> str:
    """Render any tool failure as a ``ToolMessage`` the model can relay, instead
    of letting it crash the run.

    langgraph's default handler only catches arg-validation
    (``ToolInvocationError``) and re-raises everything else — so the
    ``ToolException`` our tools raise on an upstream outage (e.g. Open-Meteo
    timing out) would otherwise propagate out of ``astream`` and 500 the whole
    ``/agent/stream`` request. Annotating ``exc: Exception`` tells ToolNode's
    ``_infer_handled_types`` to catch every tool error.

    Breadth is deliberate; the *verdict* is not. This used to label every caught
    failure "a temporary upstream problem … try again shortly", so a
    deterministic failure was narrated to the traveller as an outage with advice
    that could never work (#113). The wording now comes from
    :func:`app.agents.retry.describe_tool_failure`, shared with the
    ``ToolFaultPolicy`` hook so both paths give one answer per failure class.

    :param exc: The exception raised by a tool call.
    :return: A user-safe message describing the failure.
    """
    return describe_tool_failure(exc)


def _tools_needing_trip(tools: list[BaseTool]) -> frozenset[str]:
    """Names of tools whose ``trip_id`` comes from ``InjectedState``.

    Derived from the annotations rather than hardcoded, so a new trip-scoped
    tool is covered the day it is written instead of the day someone remembers
    to add it to a list.

    :param tools: The sub-agent's bound tools.
    :return: The names of tools that cannot run without an active trip.
    """
    names: set[str] = set()
    for tool in tools:
        fn = tool.coroutine or tool.func
        try:
            hints = typing.get_type_hints(fn, include_extras=True)
        except Exception:  # noqa: BLE001 — never block graph build on one odd tool
            hints = {}
        # Fail open, but not silently. A tool we cannot introspect is simply
        # absent from the guard, so if it *is* trip-scoped the block quietly stops
        # happening. Both ways that occurs are caught here: annotations that will
        # not resolve (a wrapper carries the strings but not the globals that
        # define them), and annotations lost entirely (a plain wrapper). No hints
        # at all is the tell — @tool needs annotations to build a schema, so every
        # one of the 33 registered tools has some; zero means they were stripped.
        # (Not `tool.args`: that hides injected params, so it is empty for exactly
        # the trip-scoped tools this guard exists to protect.)
        if not hints:
            logger.warning(
                "[agent] cannot read annotations for tool %r — excluded from the "
                "trip guard; if it is trip-scoped it will NOT be blocked when no "
                "trip is selected",
                getattr(tool, "name", fn),
            )
            continue
        for hint in hints.values():
            for meta in getattr(hint, "__metadata__", ()):
                if isinstance(meta, InjectedState) and getattr(meta, "field", None) == (
                    "trip_id"
                ):
                    names.add(tool.name)
    return frozenset(names)


def _make_trip_guard(needing_trip: frozenset[str]):
    """Return the node that stops trip-scoped calls when no trip is selected (#113).

    Without this, the call reaches ``ToolNode`` and fails validation because the
    injected ``trip_id`` is absent. That failure is only *described* to the model
    ("ask the traveller which trip") — which leaves the outcome to whether the
    model obeys prose, and a model that ignores it can call the same tool again.
    The guard makes it a graph fact instead: ``awaiting_user`` is set exactly as
    ``needs_clarification`` sets it, so reflection ends the turn before judging it
    and the traveller is asked, deterministically.

    Runs *before* the tools node, so the blocked tool never executes.

    :param needing_trip: Names of tools that require an active trip.
    :return: A node function ``trip_guard(state) -> Command``.
    """

    def trip_guard(state: TravelAgentState) -> Command:
        if not needing_trip or state.get("trip_id"):
            return Command(goto="tools")

        last = state["messages"][-1]
        calls = list(getattr(last, "tool_calls", None) or [])
        blocked = [tc for tc in calls if tc.get("name") in needing_trip]
        if not blocked:
            return Command(goto="tools")

        logger.info(
            "[agent] trip_guard → assistant (no active trip; blocked %d call(s))",
            len(blocked),
        )
        # Every pending call needs a paired ToolMessage or the provider rejects
        # the next assistant turn — including the calls that were not blocked,
        # which are abandoned with the rest of the turn.
        messages = [
            ToolMessage(
                content=(
                    NO_ACTIVE_TRIP_MSG
                    if tc.get("name") in needing_trip
                    else (
                        "Not run — this turn is blocked on the traveller "
                        "identifying which trip they mean."
                    )
                ),
                tool_call_id=tc["id"],
                name=tc.get("name"),
                status="error",
            )
            for tc in calls
        ]
        return Command(
            goto="assistant",
            update={"awaiting_user": True, "messages": messages},
        )

    return trip_guard


def build_subagent(
    name: str,
    tools: list[BaseTool],
    resolve_model: Callable[[str | None], BaseChatModel],
    prompt: str,
    tool_fault: ToolFaultPolicy | None = None,
):
    """Compile a ReAct subgraph for one specialist domain.

    ``resolve_model`` is called per-request inside the ``assistant`` node with
    the ``AgentContext.model`` hint from the current invocation, so the chat
    model is selected at runtime rather than at build time (D1 deferred binding).
    When the runtime context carries no model hint (``None``) the resolver falls
    back to the per-agent default — preserving today's behavior.

    The shared ``communication_style`` guideline is prepended to every domain
    prompt so all user-facing replies stay warm, concise, and travel-focused —
    translating raw tool data into useful guidance rather than dumping it.

    :param name: The sub-agent's name, used as the compiled graph's node name.
    :param tools: Domain tools bound to the ``assistant`` node (filtered by
        context flags at invoke time).
    :param resolve_model: Callable resolving an ``AgentContext.model`` hint to a
        chat model, called per request inside ``assistant``.
    :param prompt: The domain-specific system prompt appended to the shared
        communication-style guideline.
    :return: The compiled ReAct subgraph for this sub-agent.
    """
    # MIN-68: every specialist can signal "blocked on the traveller" so
    # reflection ends the turn before judging the clarifying question.
    # Appended here (not in the tool registry) so it stays off MCP/manifest.
    tools = [*tools, needs_clarification]

    style = registry.get("communication_style")
    system = SystemMessage(content=f"{style}\n\n{prompt}")

    def assistant(state: TravelAgentState, runtime: Runtime[AgentContext]) -> dict:
        logger.info("[agent] node=%s (assistant)", name)
        ctx = runtime.context if runtime.context is not None else None
        allow_episodic = ctx.allow_episodic if ctx is not None else True

        model = resolve_model(None)

        # Filter the episodic-recall tool when the context disables it.
        active_tools = [
            t for t in tools if (allow_episodic or t.name != EPISODIC_TOOL_NAME)
        ]
        bound = model.bind_tools(active_tools) if active_tools else model

        tz = ctx.timezone if ctx is not None else None
        system_msg = system_with_summary(state, ground_current_date(system, tz))
        # Every sub-agent replies in the supervisor-detected conversation language
        # (state["language"]) — one detection, one source of truth. Also closes the
        # clarification path (MIN-68), which skips reflection's language guard.
        system_msg = with_reply_language(system_msg, state)
        response = bound.invoke([system_msg, *state["messages"]])
        tool_calls = getattr(response, "tool_calls", None)
        if tool_calls:
            logger.info("[agent] %s → tools (%d call(s))", name, len(tool_calls))
        return {"messages": [response]}

    builder = StateGraph(TravelAgentState, context_schema=AgentContext)
    builder.add_node("assistant", assistant, retry_policy=LLM_RETRY)
    builder.add_edge(START, "assistant")

    if tools:
        if tool_fault is None:
            builder.add_node(
                "tools", ToolNode(tools, handle_tool_errors=_tool_error_to_message)
            )
        else:
            builder.add_node(
                "tools",
                ToolNode(tools, handle_tool_errors=tool_fault.handle_tool_errors),
                retry_policy=tool_fault.retry_policy,
                error_handler=tool_fault.error_handler,
            )
        # #113: a trip-scoped tool called with no active trip is stopped here,
        # before it can fail arg validation and leave the outcome to whether the
        # model obeys a prose instruction. tools_condition still decides whether
        # there is tool work at all; the guard decides whether it may run.
        needing_trip = _tools_needing_trip(tools)
        builder.add_node(
            "trip_guard",
            _make_trip_guard(needing_trip),
            destinations=("tools", "assistant"),
        )
        # tools_condition -> "tools" when the last message has tool calls, else END.
        builder.add_conditional_edges(
            "assistant", tools_condition, {"tools": "trip_guard", END: END}
        )
        builder.add_edge("tools", "assistant")
    else:
        builder.add_edge("assistant", END)

    return builder.compile(name=name)
