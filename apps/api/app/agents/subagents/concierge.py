"""Concierge sub-agent (specs/travel-agent Task 5.2)."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.subagents._base import build_subagent
from app.prompts.registry import registry
from app.tools.registry import get_tools_for


def build_concierge(llm: BaseChatModel):
    """Compile the concierge sub-agent (place/weather tools + RAG retrieval)."""
    return build_subagent(
        "concierge", get_tools_for("concierge"), llm, registry.get("concierge")
    )
