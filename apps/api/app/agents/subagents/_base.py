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
from langgraph.prebuilt.tool_node import ToolInvocationError
from langgraph.runtime import Runtime

from app.agents.constants import EPISODIC_TOOL_NAME
from app.agents.context import AgentContext
from app.agents.retry import LLM_RETRY, ToolFaultPolicy
from app.agents.state import (
    TravelAgentState,
    ground_current_date,
    system_with_summary,
    with_reply_language,
)
from app.exceptions import AppError, UpstreamError
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
    that could never work (#113). Each class now gets the recovery it actually
    has:

    * ``ToolInvocationError`` with model-fixable errors → correct the arguments.
    * ``ToolInvocationError`` with none → the only unmet requirements are
      ``InjectedState``/``InjectedStore`` args, which the model cannot supply, so
      langgraph filters them out and leaves an empty error list. That means a
      runtime precondition is missing (typically no active trip), and the fix is
      to ask the traveller — never to claim an outage.
    * ``UpstreamError`` cause → genuinely transient; keep the old wording.
    * any other ``AppError`` cause → a deterministic domain error whose message
      already carries ``detail`` + ``hint`` from :func:`app.tools._base.tool_error`.

    :param exc: The exception raised by a tool call.
    :return: A user-safe message describing the failure.
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
    if isinstance(cause, UpstreamError):
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
    return (
        f"Tool call failed: {exc}. The cause is unknown — do not claim an outage "
        "and do not retry blindly; tell the user this step did not work and, if "
        "you need something from them to proceed, ask for it."
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
    # MIN-68: every specialist can signal "blocked on the traveller" so
    # dispatch_next abandons the remaining ledger instead of draining it.
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
        # tools_condition -> "tools" when the last message has tool calls, else END.
        builder.add_conditional_edges("assistant", tools_condition)
        builder.add_edge("tools", "assistant")
    else:
        builder.add_edge("assistant", END)

    return builder.compile(name=name)
