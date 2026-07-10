"""Shared agent graph state (specs/travel-agent Task 5.1).

``TravelAgentState`` is the object LangGraph serialises into the checkpoint after
every node, so it stays small and JSON-able. ``messages`` carries the
conversation (with the ``add_messages`` reducer from ``MessagesState``); the rest
is working state the supervisor and sub-agents read and update.
"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.messages import SystemMessage
from langgraph.graph import MessagesState


class TravelAgentState(MessagesState):
    """Conversation + working state for the travel agent.

    Inherits ``messages: Annotated[list, add_messages]`` from ``MessagesState``.
    """

    user_id: str
    trip_id: str | None
    current_flow: str  # which sub-agent the supervisor routed to
    language: (
        str  # dominant conversation language code (e.g. "en"/"vi"); set by supervisor
    )
    summary: str  # rolling summary of compressed older turns
    revisions: int  # reflection self-correction counter (bounds the loop)
    # MIN-59 rubric grader. Deliberately NOT ``revisions``: sharing that counter let a
    # grader revision on booking/concierge push it past reflection's cap, silently
    # disabling reflection for every later turn of the conversation. Reset per turn in
    # ``load_context_node`` — a turn-scoped counter must actually be turn-scoped.
    grader_iterations: int
    grader_verdict: str | None  # last GraderVerdict value; measurement surface
    trip_context: str  # active-trip snapshot; injected at model call, not into messages
    instructions: (
        str  # standing procedural instructions; folded into leading system message
    )
    profile: (
        str  # personalization block (name/gender/travel-group); injected at model call
    )
    plan_approved: bool  # P2: HITL plan-approval signal → episode outcome="approved"


def system_with_summary(state: TravelAgentState, base: SystemMessage) -> SystemMessage:
    """Fold ``profile``, ``instructions``, ``trip_context`` and ``summary`` into one leading system prompt.

    REVIEW.md C2: the rolling ``summary`` must be re-injected after compression.
    REVIEW.md M2: the trip-context snapshot must appear *before* the HumanMessage,
    not appended to ``messages`` via the ``add_messages`` reducer (which would place
    it *after* the HumanMessage and upset Anthropic's single-system-message rule).

    The traveller ``profile`` is folded first — before instructions — so name/gender
    carry the most weight for address/tone. Procedural instructions (per-user
    standing directives) are folded before the summary so they carry the most weight.

    :param state: The current graph state, read for ``profile``, ``instructions``,
        ``trip_context`` and ``summary``.
    :param base: The base system message to fold the extra context into.
    :return: ``base`` unchanged when none of the four fields are set, else one
        ``SystemMessage`` combining base + profile + instructions + trip_context +
        summary — a single leading system message keeps providers that reject
        mid-stream/multiple system messages happy.
    """
    trip_context = state.get("trip_context")
    summary = state.get("summary")
    instructions = state.get("instructions")
    profile = state.get("profile")
    if not trip_context and not summary and not instructions and not profile:
        return base
    parts = [base.content]
    if profile:
        parts.append(f"Traveller profile:\n{profile}")
    if instructions:
        parts.append(f"Standing traveller instructions:\n{instructions}")
    if trip_context:
        parts.append(f"Current trip context:\n{trip_context}")
    if summary:
        parts.append(f"Summary of earlier conversation:\n{summary}")
    return SystemMessage(content="\n\n".join(parts))


def ground_current_date(base: SystemMessage) -> SystemMessage:
    """Prepend today's date so the model resolves relative dates instead of guessing.

    Without a concrete "today", the model has to invent a date when the traveller
    says something like "hôm nay"/"today" or "next Friday", which then flows into
    tool calls such as ``search_flights(departure_date=...)``. Grounding a real date
    lets it resolve those expressions and forbids fabricating a date that was never
    given. Computed per request — the graph is built once at startup, so a long-
    running server would otherwise serve a date frozen at boot.

    :param base: The base system message to fold the date grounding into.
    :return: A ``SystemMessage`` with ``base`` followed by the date-grounding note.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    note = (
        f"CURRENT DATE: today is {today} (UTC). This is the only correct value for "
        '"today". Resolve every relative date ("today", "tomorrow", "next Friday", '
        '"this weekend") against it, and never pass a tool a date earlier than '
        f"{today}. If the traveller has not given enough to derive a concrete date, "
        "ask them — do not guess or invent one."
    )
    return SystemMessage(content=f"{note}\n\n{base.content}")
