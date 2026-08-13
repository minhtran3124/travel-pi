"""Synthesis worker for GH-117 Path A.

A synthesis worker is a per-specialist ReAct subgraph that gathers facts with tools
and returns a structured ``TaskResult``. The worker is invoked once per task via
LangGraph's ``Send`` API, so multiple specialists can run in parallel. Their
results are collected in ``TravelAgentState.task_results`` and later combined by
the ``synthesize`` node.

The worker reuses the existing specialist sub-agent (prose) as an inner subgraph,
then extracts a structured result from its final answer. This keeps the worker
prompts, tools, and tool-fault policies identical to the production sub-agents.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

from app.agents.context import AgentContext
from app.agents.state import TravelAgentState
from app.agents.subagents.booking import build_booking
from app.agents.subagents.budget import build_budget
from app.agents.subagents.concierge import build_concierge
from app.agents.subagents.journal import build_journal
from app.agents.subagents.planner import build_planner

# Map specialist names to their compiled-subagent builder.
_AGENT_BUILDERS: dict[
    str, Callable[[Callable[[str | None], BaseChatModel]], Any]
] = {
    "planner": build_planner,
    "concierge": build_concierge,
    "journal": build_journal,
    "booking": build_booking,
    "budget": build_budget,
}


def _resolve_for_agent(
    name: str,
    resolve_model: Callable[[str | None], BaseChatModel],
) -> Callable[[str | None], BaseChatModel]:
    """Return a resolver that always hands back the model for ``name``.

    The inner sub-agent will call its resolver with its own name, but we want it
    to use the same model configuration as the worker's requested specialist.
    """

    def resolve(_hint: str | None = None) -> BaseChatModel:
        return resolve_model(None)

    return resolve


def _last_assistant_content(messages: list[Any]) -> str:
    """Return the content of the last content-bearing AIMessage, or empty."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "content", None):
            return str(msg.content)
    return ""


def build_synthesis_worker(
    llm: BaseChatModel,
) -> Callable[[TravelAgentState, Runtime[AgentContext]], Command]:
    """Return a sync worker node that runs one specialist and returns a result.

    The returned node is intended to be added once to the parent graph under the
    name ``synthesis_worker``. It reads ``state["task"]`` to determine which
    specialist to invoke.

    :param llm: Chat model used by every specialist worker.
    :return: A sync node function.
    """

    def worker(state: TravelAgentState, runtime: Runtime[AgentContext]) -> Command:
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
                goto="synthesize",
            )

        subagent = builder(lambda _hint=None: llm)
        # Run the inner sub-agent graph. We pass the current conversation plus
        # the task so the specialist has full context. The inner graph appends
        # its prose answer to its own messages copy; we extract that answer as
        # the structured finding and do NOT propagate the inner messages back to
        # the parent state.
        inner_state = dict(state)
        inner_state["task"] = task
        inner_state["current_flow"] = agent_name
        result = subagent.invoke(inner_state, config=getattr(runtime, "config", None))
        findings = _last_assistant_content(result.get("messages", []))
        return Command(
            update={
                "task_results": [
                    {"agent": agent_name, "index": index, "findings": findings}
                ]
            },
            goto="synthesize",
        )

    return worker
