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
from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime

from app.agents.constants import EPISODIC_TOOL_NAME
from app.agents.context import AgentContext
from app.agents.retry import LLM_RETRY, ToolFaultPolicy
from app.agents.state import (
    TravelAgentState,
    ground_current_date,
    system_with_summary,
)
from app.prompts.registry import registry

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

    :param exc: The exception raised by a tool call.
    :return: A user-safe message describing the failure.
    """
    return (
        f"Tool call failed: {exc}. This is a temporary upstream problem, not a "
        "bad request — do not retry the tool; tell the user the information is "
        "currently unavailable and to try again shortly."
    )


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

        response = bound.invoke(
            [
                system_with_summary(state, ground_current_date(system)),
                *state["messages"],
            ]
        )
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
        # tools_condition -> "tools" when the last message has tool calls, else END.
        builder.add_conditional_edges("assistant", tools_condition)
        builder.add_edge("tools", "assistant")
    else:
        builder.add_edge("assistant", END)

    return builder.compile(name=name)
