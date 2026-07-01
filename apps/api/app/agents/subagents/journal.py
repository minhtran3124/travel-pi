"""Journal sub-agent (specs/travel-agent Task 5.2)."""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.subagents._base import build_subagent
from app.prompts.registry import registry
from app.tools.registry import get_tools_for


def build_journal(resolve_model: Callable[[str | None], BaseChatModel]):
    """Compile the journal sub-agent (trip-edit + long-term memory tools).

    :param resolve_model: Callable resolving an ``AgentContext.model`` hint to a
        chat model, called per request inside the sub-agent's ``assistant`` node.
    :return: The compiled ReAct subgraph for this sub-agent.
    """
    return build_subagent(
        "journal", get_tools_for("journal"), resolve_model, registry.get("journal")
    )
