"""Shared agent graph state (specs/travel-agent Task 5.1).

``TravelAgentState`` is the object LangGraph serialises into the checkpoint after
every node, so it stays small and JSON-able. ``messages`` carries the
conversation (with the ``add_messages`` reducer from ``MessagesState``); the rest
is working state the supervisor and sub-agents read and update.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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


def ground_current_date(base: SystemMessage, tz: str | None = None) -> SystemMessage:
    """Prepend today's date and point relative-date resolution at the resolve_date tool.

    Without a concrete "today", the model has no anchor for expressions like
    "hôm nay"/"today" or "next Friday", which then flow into tool calls such as
    ``search_flights(departure_date=...)``. Grounding a real date gives it that
    anchor; the note also routes non-ISO date expressions through the
    ``resolve_date`` tool instead of letting the model compute them itself, and
    tells it to state the resolved date rather than ask the traveller to
    confirm it — asking is reserved for no date signal at all, or an ambiguous
    expression ``resolve_date`` itself reports. Computed per request — the
    graph is built once at startup, so a long-running server would otherwise
    serve a date frozen at boot.

    :param base: The base system message to fold the date grounding into.
    :param tz: Optional IANA timezone (e.g. "Asia/Ho_Chi_Minh") for the traveller;
        grounds "today" in their local zone. Invalid/None falls back to UTC.
    :return: A ``SystemMessage`` with ``base`` followed by the date-grounding note.
    """
    zone_label = "UTC"
    now = datetime.now(timezone.utc)
    if tz:
        try:
            now = datetime.now(ZoneInfo(tz))
            zone_label = tz
        except Exception:  # unknown/invalid tz -> keep UTC
            now = datetime.now(timezone.utc)
            zone_label = "UTC"
    today = now.strftime("%Y-%m-%d")
    note = (
        f"CURRENT DATE: today is {today} ({zone_label}). This is the only correct "
        'value for "today", and never pass a tool a date earlier than '
        f'{today}. Resolve relative, weekday, or partial dates ("tomorrow", '
        '"next Friday", "thứ 6 tuần sau", "12/07") with the resolve_date tool — '
        "do not compute them yourself. Do not ask the traveller to confirm a date "
        "resolve_date already returned; state it in your answer so they can "
        "correct it. If the traveller mentioned NO date at all, you MUST ask which "
        f"date they want — never fall back to {today}, and never invent a date they "
        "did not give. Ask, too, when resolve_date reports the expression is "
        "ambiguous."
    )
    return SystemMessage(content=f"{note}\n\n{base.content}")
