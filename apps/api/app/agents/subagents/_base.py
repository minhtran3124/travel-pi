"""Sub-agent factory (specs/travel-agent Task 5.1).

A specialist sub-agent is a small ReAct subgraph: an ``assistant`` node binds the
domain's tools and answers; if it emits tool calls, ``ToolNode`` runs them
(catching ``ToolException`` -> ``ToolMessage(status="error")`` so the model can
self-correct) and control returns to the assistant; otherwise the loop ends.

Compiled subgraphs are added as nodes to the supervisor graph (Task 5.4); the
parent's checkpointer and store propagate into these nested nodes at runtime, so
tools using ``InjectedStore`` work without per-sub-agent wiring.

C.1 (specs/runtime-context-config): ``build_subagent`` now accepts a
``resolve_model`` callable instead of a fixed ``llm``. The ``assistant`` node
resolves + binds the model **per request** from ``runtime.context.model``, so the
sub-agent's chat model can be selected at invoke time from ``AgentContext``.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime

from app.agents.context import AgentContext
from app.agents.state import TravelAgentState, system_with_summary
from app.enums import ResponseStyle
from app.prompts.registry import registry

# Name of the RAG retrieval tool (app/tools/rag_tools.py); used to gate it
# when runtime.context.allow_rag is False (fast mode / free-tier constraint).
RAG_TOOL_NAME = "search_destination_knowledge"


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
    resolve_model: Callable[[str | None], BaseChatModel],
    prompt: str,
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
    """
    style = registry.get("communication_style")
    system = SystemMessage(content=f"{style}\n\n{prompt}")

    def assistant(state: TravelAgentState, runtime: Runtime[AgentContext]) -> dict:
        ctx = runtime.context if runtime.context is not None else None
        ctx_model = ctx.model if ctx is not None else None
        allow_rag = ctx.allow_rag if ctx is not None else True
        response_style = (
            ctx.response_style if ctx is not None else ResponseStyle.DEFAULT
        )

        model = resolve_model(ctx_model)

        # Filter the RAG retrieval tool when the context disables it (e.g. fast mode).
        active_tools = [t for t in tools if allow_rag or t.name != RAG_TOOL_NAME]
        bound = model.bind_tools(active_tools) if active_tools else model

        # Inject a style directive into the system prompt based on response_style.
        if response_style == ResponseStyle.CONCISE:
            effective_system = SystemMessage(content=system.content + "\n\nBe brief.")
        elif response_style == ResponseStyle.DETAILED:
            effective_system = SystemMessage(
                content=system.content + "\n\nBe thorough."
            )
        else:
            effective_system = system

        response = bound.invoke(
            [system_with_summary(state, effective_system), *state["messages"]]
        )
        return {"messages": [response]}

    builder = StateGraph(TravelAgentState, context_schema=AgentContext)
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
