"""Shared agent graph state (specs/travel-agent Task 5.1).

``TravelAgentState`` is the object LangGraph serialises into the checkpoint after
every node, so it stays small and JSON-able. ``messages`` carries the
conversation (with the ``add_messages`` reducer from ``MessagesState``); the rest
is working state the supervisor and sub-agents read and update.
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langgraph.graph import MessagesState


class TravelAgentState(MessagesState):
    """Conversation + working state for the travel agent.

    Inherits ``messages: Annotated[list, add_messages]`` from ``MessagesState``.
    """

    user_id: str
    trip_id: str | None
    current_flow: str  # which sub-agent the supervisor routed to
    summary: str  # rolling summary of compressed older turns
    revisions: int  # reflection self-correction counter (bounds the loop)


def system_with_summary(state: TravelAgentState, base: SystemMessage) -> SystemMessage:
    """Fold the rolling ``summary`` into the system prompt (REVIEW.md C2).

    The ``summarize`` node compresses old turns into ``state["summary"]`` and drops
    them from ``messages``; without re-injecting that summary the model loses the
    compressed context entirely. Returns ``base`` unchanged when no summary is set,
    else one ``SystemMessage`` combining the base prompt and the summary (a single
    system message keeps providers that reject mid-stream/multiple system messages
    happy).
    """
    summary = state.get("summary")
    if not summary:
        return base
    return SystemMessage(
        content=f"{base.content}\n\nSummary of earlier conversation:\n{summary}"
    )
