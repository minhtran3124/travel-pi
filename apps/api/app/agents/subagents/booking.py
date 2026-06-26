"""Booking sub-agent (specs/travel-agent Task 5.2).

Handles quote-then-book. The booking tools guard destructive actions (book_hotel
requires confirm=true), giving a human-in-the-loop checkpoint before any
reservation is made.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.subagents._base import build_subagent
from app.prompts.registry import registry
from app.tools.registry import get_tools_for


def build_booking(llm: BaseChatModel):
    """Compile the booking sub-agent (flight/hotel search + guarded booking)."""
    return build_subagent(
        "booking", get_tools_for("booking"), llm, registry.get("booking")
    )
