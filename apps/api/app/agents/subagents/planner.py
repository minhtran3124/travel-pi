"""Planner sub-agent (specs/travel-agent Task 5.2)."""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.subagents._base import build_subagent
from app.prompts.registry import registry
from app.tools.registry import get_tools_for


def build_planner(resolve_model: Callable[[str | None], BaseChatModel]):
    """Compile the planner sub-agent (trip/place/flight/hotel/weather tools)."""
    return build_subagent(
        "planner", get_tools_for("planner"), resolve_model, registry.get("planner")
    )
