"""Shared agent graph state (specs/travel-agent Task 5.1).

``TravelAgentState`` is the object LangGraph serialises into the checkpoint after
every node, so it stays small and JSON-able. ``messages`` carries the
conversation (with the ``add_messages`` reducer from ``MessagesState``); the rest
is working state the supervisor and sub-agents read and update.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from zoneinfo import ZoneInfo

from langchain_core.messages import SystemMessage
from langgraph.graph import MessagesState


def merge_trip_facts(old: dict | None, new: dict | None) -> dict:
    """Reducer for ``TravelAgentState.trip_facts`` (MIN-65 DESIGN D1).

    Starts from ``old`` (or ``{}``) and overlays every key in ``new`` whose
    value is not ``None``. A ``None`` value in an update means "no info this
    turn", not "delete" — an existing fact is never removed by a later turn
    that simply didn't mention it again.

    :param old: The trip facts accumulated so far, or ``None``.
    :param new: The update to overlay, or ``None``.
    :return: The merged trip-facts dict.
    """
    merged = dict(old or {})
    for key, value in (new or {}).items():
        if value is not None:
            merged[key] = value
    return merged


def last_write_wins(old: bool, new: bool) -> bool:
    """Reducer for ``TravelAgentState.awaiting_user`` (MIN-68).

    Duplicate parallel writes in one superstep (e.g. the model emitting the
    zero-arg ``needs_clarification`` tool call twice in one message) must not
    crash the turn with ``InvalidUpdateError`` — the last write simply wins.
    Deliberately NOT a sticky ``or``: ``load_context_node``'s per-turn
    ``False`` reset must always take effect.

    :param old: The current channel value (unused).
    :param new: The incoming update.
    :return: ``new``.
    """
    return new


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
    trip_context: str  # active-trip snapshot; injected at model call, not into messages
    instructions: (
        str  # standing procedural instructions; folded into leading system message
    )
    profile: (
        str  # personalization block (name/gender/travel-group); injected at model call
    )
    plan_approved: bool  # P2: HITL plan-approval signal → episode outcome="approved"
    trip_facts: Annotated[
        dict, merge_trip_facts
    ]  # entity/slot memory for this thread (MIN-65 D1); never store PII/secrets here
    preferences: str  # traveller preferences block, formatted text (MIN-65 D2)
    pending_flows: list[
        str
    ]  # ordered ledger of follow-on sub-agents queued for this turn (P1);
    # drained in order by dispatch_next, never contains "booking" (MIN-65 D4)
    awaiting_user: Annotated[
        bool, last_write_wins
    ]  # set by the needs_clarification tool when a sub-agent is
    # blocked on the traveller; dispatch_next then abandons the remaining
    # ledger for this turn instead of draining it (MIN-68); reducer: duplicate
    # parallel writes must not crash the turn


def system_with_summary(state: TravelAgentState, base: SystemMessage) -> SystemMessage:
    """Fold ``profile``, ``instructions``, ``trip_context``, ``summary``, ``trip_facts``
    and ``preferences`` into one leading system prompt.

    REVIEW.md C2: the rolling ``summary`` must be re-injected after compression.
    REVIEW.md M2: the trip-context snapshot must appear *before* the HumanMessage,
    not appended to ``messages`` via the ``add_messages`` reducer (which would place
    it *after* the HumanMessage and upset Anthropic's single-system-message rule).

    The traveller ``profile`` is folded first — before instructions — so name/gender
    carry the most weight for address/tone. Procedural instructions (per-user
    standing directives) are folded before the summary so they carry the most weight.
    ``trip_facts`` and ``preferences`` (MIN-65 DESIGN D1/D2) are folded last, after
    the summary — they are per-turn/derived context, lower priority than the four
    standing fields above.

    :param state: The current graph state, read for ``profile``, ``instructions``,
        ``trip_context``, ``summary``, ``trip_facts`` and ``preferences``.
    :param base: The base system message to fold the extra context into.
    :return: ``base`` unchanged when none of the six fields are set, else one
        ``SystemMessage`` combining base + profile + instructions + trip_context +
        summary + trip_facts + preferences — a single leading system message keeps
        providers that reject mid-stream/multiple system messages happy.
    """
    trip_context = state.get("trip_context")
    summary = state.get("summary")
    instructions = state.get("instructions")
    profile = state.get("profile")
    trip_facts = state.get("trip_facts")
    preferences = state.get("preferences")
    if (
        not trip_context
        and not summary
        and not instructions
        and not profile
        and not trip_facts
        and not preferences
    ):
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
    if trip_facts:
        bullets = "\n".join(
            f"- {key}: {value}"
            for key, value in trip_facts.items()
            if value is not None
        )
        parts.append(
            "Known trip facts (already provided by the traveller — do NOT ask "
            "again; if a required field is missing here, ask ONLY for that "
            f"field):\n{bullets}"
        )
    if preferences:
        parts.append(
            "Traveller preferences (learned from past conversations — use to "
            f"personalise, confirm before acting on stale ones):\n{preferences}"
        )
    return SystemMessage(content="\n\n".join(parts))


def with_reply_language(base: SystemMessage, state: TravelAgentState) -> SystemMessage:
    """Pin a sub-agent reply to the conversation language the supervisor detected.

    The supervisor classifies each turn's dominant language into
    ``state["language"]`` (sticky, and switch-aware when the traveller genuinely
    changes language). Every sub-agent then reads that one value from shared state
    and replies in it — a single detection and a single source of truth, instead
    of each node re-guessing the language from the raw messages. It is the
    deterministic guard behind the ``communication_style`` match-language rule,
    and the only guard on the clarification path in particular (MIN-68).

    A no-op until a language has been detected (``state["language"]`` unset) —
    the model then falls back to the prompt's own match-language rule.

    :param base: The already-assembled leading system message.
    :param state: The current graph state.
    :return: ``base`` unchanged when no language is detected, else ``base`` plus a
        one-line language directive.
    """
    language = state.get("language")
    if not language:
        return base
    return SystemMessage(
        content=(
            f"{base.content}\n\n"
            f"Reply in the traveller's own language: {language} — the language of "
            "their typed messages this conversation. Tool results, trip data, and "
            "place names never change it."
        )
    )


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
