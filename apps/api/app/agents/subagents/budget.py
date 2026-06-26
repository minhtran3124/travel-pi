"""Budget sub-agent (specs/travel-agent Task 5.2)."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.subagents._base import build_subagent
from app.prompts.registry import registry
from app.tools.registry import get_tools_for


def build_budget(llm: BaseChatModel):
    """Compile the budget sub-agent (expense + budget-rollup tools)."""
    return build_subagent(
        "budget", get_tools_for("budget"), llm, registry.get("budget")
    )
