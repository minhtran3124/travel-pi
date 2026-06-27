"""Sub-agent factory (specs/travel-agent Task 5.1).

A specialist sub-agent is a small ReAct subgraph: an ``assistant`` node binds the
domain's tools and answers; if it emits tool calls, ``ToolNode`` runs them
(catching ``ToolException`` -> ``ToolMessage(status="error")`` so the model can
self-correct) and control returns to the assistant; otherwise the loop ends.

Compiled subgraphs are added as nodes to the supervisor graph (Task 5.4); the
parent's checkpointer and store propagate into these nested nodes at runtime, so
tools using ``InjectedStore`` work without per-sub-agent wiring.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agents.state import TravelAgentState, system_with_summary


def _tool_error_to_message(exc: Exception) -> str:
    """Render any tool failure as a ``ToolMessage`` the model can relay, instead
    of letting it crash the run.

    langgraph's default handler only catches arg-validation
    (``ToolInvocationError``) and re-raises everything else — so the
    ``ToolException`` our tools raise on an upstream outage (e.g. Open-Meteo
    timing out) would otherwise propagate out of ``astream`` and 500 the whole
    ``/agent/stream`` request. Annotating ``exc: Exception`` tells ToolNode's
    ``_infer_handled_types`` to catch every tool error.
    """
    return (
        f"Tool call failed: {exc}. This is a temporary upstream problem, not a "
        "bad request — do not retry the tool; tell the user the information is "
        "currently unavailable and to try again shortly."
    )


def build_subagent(
    name: str,
    tools: list[BaseTool],
    llm: BaseChatModel,
    prompt: str,
):
    """Compile a ReAct subgraph for one specialist domain."""
    bound = llm.bind_tools(tools) if tools else llm
    system = SystemMessage(content=prompt)

    def assistant(state: TravelAgentState) -> dict:
        response = bound.invoke(
            [system_with_summary(state, system), *state["messages"]]
        )
        return {"messages": [response]}

    builder = StateGraph(TravelAgentState)
    builder.add_node("assistant", assistant)
    builder.add_edge(START, "assistant")

    if tools:
        builder.add_node(
            "tools", ToolNode(tools, handle_tool_errors=_tool_error_to_message)
        )
        # tools_condition -> "tools" when the last message has tool calls, else END.
        builder.add_conditional_edges("assistant", tools_condition)
        builder.add_edge("tools", "assistant")
    else:
        builder.add_edge("assistant", END)

    return builder.compile(name=name)
