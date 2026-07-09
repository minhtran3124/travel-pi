"""Concierge sub-agent (specs/travel-agent Task 5.2)."""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.retry import TOOL_FAULT
from app.agents.subagents._base import build_subagent
from app.prompts.registry import registry
from app.tools.registry import get_tools_for


def build_concierge(resolve_model: Callable[[str | None], BaseChatModel]):
    """Compile the concierge sub-agent (knowledge retrieval + place/weather tools).

    :param resolve_model: Callable resolving an ``AgentContext.model`` hint to a
        chat model, called per request inside the sub-agent's ``assistant`` node.
    :return: The compiled ReAct subgraph for this sub-agent.
    """
    return build_subagent(
        "concierge",
        get_tools_for("concierge"),
        resolve_model,
        registry.get("concierge"),
        tool_fault=TOOL_FAULT,
    )
