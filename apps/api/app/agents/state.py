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
    trip_context: str  # active-trip snapshot; injected at model call, not into messages
    instructions: str  # standing procedural instructions; folded into leading system message


def system_with_summary(state: TravelAgentState, base: SystemMessage) -> SystemMessage:
    """Fold ``instructions``, ``trip_context`` and ``summary`` into one leading system prompt.

    REVIEW.md C2: the rolling ``summary`` must be re-injected after compression.
    REVIEW.md M2: the trip-context snapshot must appear *before* the HumanMessage,
    not appended to ``messages`` via the ``add_messages`` reducer (which would place
    it *after* the HumanMessage and upset Anthropic's single-system-message rule).

    Procedural instructions (per-user standing directives) are folded before the
    summary so they carry the most weight.

    Returns ``base`` unchanged when none of the three fields are set, else one
    ``SystemMessage`` combining base + instructions + trip_context + summary — a
    single leading system message keeps providers that reject mid-stream/multiple
    system messages happy.
    """
    trip_context = state.get("trip_context")
    summary = state.get("summary")
    instructions = state.get("instructions")
    if not trip_context and not summary and not instructions:
        return base
    parts = [base.content]
    if instructions:
        parts.append(f"Standing traveller instructions:\n{instructions}")
    if trip_context:
        parts.append(f"Current trip context:\n{trip_context}")
    if summary:
        parts.append(f"Summary of earlier conversation:\n{summary}")
    return SystemMessage(content="\n\n".join(parts))
