"""Booking sub-agent (specs/travel-agent Task 5.2).

Handles quote-then-book. The booking tools guard destructive actions (book_hotel
requires confirm=true), giving a human-in-the-loop checkpoint before any
reservation is made.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.subagents._base import build_subagent
from app.prompts.registry import registry
from app.tools.registry import get_tools_for


def build_booking(resolve_model: Callable[[str | None], BaseChatModel]):
    """Compile the booking sub-agent (flight/hotel search + guarded booking).

    :param resolve_model: Callable resolving an ``AgentContext.model`` hint to a
        chat model, called per request inside the sub-agent's ``assistant`` node.
    :return: The compiled ReAct subgraph for this sub-agent.
    """
    return build_subagent(
        "booking", get_tools_for("booking"), resolve_model, registry.get("booking")
    )
