"""Synthesis worker for GH-117 Path A.

A synthesis worker is a per-specialist ReAct subgraph that gathers facts with tools
and returns a structured ``TaskResult``. The worker is invoked once per task via
LangGraph's ``Send`` API, so multiple specialists can run in parallel. Their
results are collected in ``TravelAgentState.task_results`` and later combined by
the ``synthesize`` node.

The worker reuses the existing specialist sub-agent (prose) as an inner subgraph,
then extracts a structured result from its final answer. This keeps the worker
prompts, tools, and tool-fault policies identical to the production sub-agents.

The node is **async** and must stay that way (#178). Several agent tools are
``async def`` — ``get_weather``, ``get_packing``, ``get_air_quality``,
``get_climate``, ``get_route``, ``get_city_route`` — and both the planner and the
concierge bind them. A sync ``subagent.invoke`` raises ``NotImplementedError:
StructuredTool does not support sync invocation`` on the first such call, which
kills the whole ``tools`` node, so ``TOOL_FAULT``'s ``graceful_fallback`` hands the
model a "temporarily unavailable" message for *every* call in that batch — healthy
synchronous siblings included. The specialist then reports a false outage that
retrying reproduces identically. The parent graph is always driven asynchronously
in production (``graph.ainvoke`` / ``graph.astream``), so this node was the single
sync link in an otherwise async chain.
"""

from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

from app.agents.constants import SYNTHESIZE_NODE
from app.agents.context import AgentContext
from app.agents.state import TravelAgentState
from app.agents.subagents.booking import build_booking
from app.agents.subagents.budget import build_budget
from app.agents.subagents.concierge import build_concierge
from app.agents.subagents.journal import build_journal
from app.agents.subagents.planner import build_planner

# Map specialist names to their compiled-subagent builder.
_AGENT_BUILDERS: dict[str, Callable[[Callable[[str | None], BaseChatModel]], Any]] = {
    "planner": build_planner,
    "concierge": build_concierge,
    "journal": build_journal,
    "booking": build_booking,
    "budget": build_budget,
}


def _last_assistant_content(messages: list[Any]) -> str:
    """Return the content of the last content-bearing AIMessage, or empty."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "content", None):
            return str(msg.content)
    return ""


def build_synthesis_worker(
    resolve_model: Callable[[str, str | None], BaseChatModel],
) -> Callable[[TravelAgentState, Runtime[AgentContext]], Awaitable[Command]]:
    """Return an async worker node that runs one specialist and returns a result.

    The returned node is intended to be added once to the parent graph under the
    name ``synthesis_worker``. It reads ``state["task"]`` to determine which
    specialist to invoke, then resolves that specialist's own model.

    :param resolve_model: Callable ``(agent_name, ctx_model_hint) -> chat_model``.
    :return: An async node coroutine function (see the module docstring: the
        specialists bind async-only tools, so the sub-agent must be awaited).
    """

    async def worker(
        state: TravelAgentState, runtime: Runtime[AgentContext]
    ) -> Command:
        task = state.get("task") or {}
        agent_name = task.get("agent", "unknown")
        index = task.get("index", 0)

        builder = _AGENT_BUILDERS.get(agent_name)
        if builder is None:
            findings = f"Unknown specialist '{agent_name}' — no facts gathered."
            return Command(
                update={
                    "task_results": [
                        {"agent": agent_name, "index": index, "findings": findings}
                    ]
                },
                goto=SYNTHESIZE_NODE,
            )

        subagent = builder(lambda hint=None: resolve_model(agent_name, hint))
        # Run the inner sub-agent graph. We pass the current conversation plus
        # the task so the specialist has full context. The inner graph appends
        # its prose answer to its own messages copy; we extract that answer as
        # the structured finding and do NOT propagate the inner messages back to
        # the parent state.
        inner_state = dict(state)
        # The parent state's message list must not be mutated by the inner
        # subgraph (add_messages reducer appends to it). Deep-copy before handing
        # it off so the worker's input remains isolated.
        inner_state["messages"] = copy.deepcopy(inner_state.get("messages", []))
        inner_state["task"] = task
        inner_state["current_flow"] = agent_name
        # The checkpoint namespace of the inner graph does not carry the
        # specialist name, so the config metadata is the only channel that
        # reaches the callback hooks (``on_chat_model_start`` / ``on_tool_start``
        # both receive ``metadata``). Merge, never replace: the caller's own
        # metadata carries the node/namespace keys the metrics handler reads.
        base_config = getattr(runtime, "config", None) or {}
        inner_config = {
            **base_config,
            "metadata": {
                **(base_config.get("metadata") or {}),
                "specialist": agent_name,
            },
        }
        result = await subagent.ainvoke(inner_state, config=inner_config)
        findings = _last_assistant_content(result.get("messages", []))

        # GH-117 Path A / Codex Comment 2: tools inside the worker may mutate
        # graph state (e.g. create_trip sets trip_id, needs_clarification sets
        # awaiting_user). Compare the inner result with the input snapshot and
        # propagate only fields that actually changed. This avoids parallel
        # workers overwriting a sibling's mutation with an unchanged value.
        state_updates: dict[str, Any] = {}
        for key in ("trip_id", "awaiting_user"):
            new_val = result.get(key)
            if new_val != inner_state.get(key):
                state_updates[key] = new_val

        return Command(
            update={
                "task_results": [
                    {"agent": agent_name, "index": index, "findings": findings}
                ],
                **state_updates,
            },
            goto=SYNTHESIZE_NODE,
        )

    return worker
