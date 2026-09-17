"""Shared agent graph state serialised into the checkpoint after every node."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import MessagesState

from app.agents.constants import TASK_NOTE_PREAMBLE


def _replace_tasks(old: list[dict] | None, new: list[dict] | None) -> list[dict]:
    """Reducer for ``tasks``: plain dicts (checkpoint serde), last-write-wins per turn."""
    return list(new or [])


def _append_results(old: list[dict] | None, new: list[dict] | None) -> list[dict]:
    """Reducer for ``task_results``: workers append; an explicit empty list resets."""
    if not new:
        return []
    return list(old or []) + list(new)


def merge_trip_facts(old: dict | None, new: dict | None) -> dict:
    """Reducer for ``trip_facts``: overlay non-``None`` keys; ``None`` means "no info
    this turn", never "delete", so a fact is not dropped by a later silent turn."""
    merged = dict(old or {})
    for key, value in (new or {}).items():
        if value is not None:
            merged[key] = value
    return merged


def last_write_wins(old: bool, new: bool) -> bool:
    """Reducer for ``awaiting_user``: last write wins, so duplicate parallel writes
    don't crash the turn. Not a sticky ``or`` — the per-turn ``False`` reset must apply."""
    return new


class TravelAgentState(MessagesState):
    """Conversation + working state for the travel agent.

    Inherits ``messages: Annotated[list, add_messages]`` from ``MessagesState``.
    """

    user_id: str
    trip_id: str | None
    current_flow: str  # which sub-agent the supervisor routed to
    language: str  # dominant conversation language code
    summary: str  # rolling summary of compressed older turns
    revisions: int  # reflection self-correction counter (bounds the loop)
    trip_context: str  # active-trip snapshot; injected at model call, not into messages
    instructions: (
        str  # standing procedural instructions; folded into leading system message
    )
    profile: (
        str  # personalization block (name/gender/travel-group); injected at model call
    )
    account_email: (
        str | None
    )  # signed-in account's email (None if anonymous); offered for booking, not asked blind
    plan_approved: bool  # HITL plan-approval signal → episode outcome="approved"
    trip_facts: Annotated[
        dict, merge_trip_facts
    ]  # entity/slot memory for this thread; never store PII/secrets here
    preferences: str  # traveller preferences block, formatted text
    awaiting_user: Annotated[
        bool, last_write_wins
    ]  # set by needs_clarification; reflection then ends the turn before judging it
    tasks: Annotated[
        list[dict], _replace_tasks
    ]  # ordered decomposition from supervisor into synthesis workers
    task_results: Annotated[
        list[dict], _append_results
    ]  # structured results gathered by parallel workers


def system_with_summary(state: TravelAgentState, base: SystemMessage) -> SystemMessage:
    """Fold profile, account_email, instructions, trip_context, summary, trip_facts
    and preferences into ONE leading system message.

    Order is priority order (profile first, derived context last). A single leading
    system message keeps providers that reject mid-stream/multiple system messages happy.
    """
    trip_context = state.get("trip_context")
    summary = state.get("summary")
    instructions = state.get("instructions")
    profile = state.get("profile")
    account_email = state.get("account_email")
    trip_facts = state.get("trip_facts")
    preferences = state.get("preferences")
    if (
        not trip_context
        and not summary
        and not instructions
        and not profile
        and not account_email
        and not trip_facts
        and not preferences
    ):
        return base
    parts = [base.content]
    if profile:
        parts.append(f"Traveller profile:\n{profile}")
    if account_email:
        parts.append(f"Signed-in account email:\n{account_email}")
    if instructions:
        parts.append(f"Standing traveller instructions:\n{instructions}")
    if trip_context:
        parts.append(
            "Current trip context (the ONE trip currently open — this is not a "
            "list of the traveller's trips, and says nothing about how many they "
            f"have):\n{trip_context}"
        )
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
    """Pin a sub-agent reply to ``state["language"]`` (the supervisor's single detection).

    The deterministic guard behind the match-language rule; matters most on the
    clarification path, which skips reflection. A no-op until a language is detected.
    """
    language = state.get("language")
    if not language:
        return base
    return SystemMessage(
        content=(
            f"{base.content}\n\n"
            f"Reply in the traveller's own language: {language} — the language of "
            "their typed messages this conversation, or the language they explicitly "
            "asked you to reply in. Tool results, trip data, and place names never "
            "change it."
        )
    )


def with_task_note(base: SystemMessage, state: TravelAgentState) -> SystemMessage:
    """Fold the specialist's task (``tasks[0].query``) into its leading system message.

    Folded in, never appended as a second system message (providers/the Anthropic
    adapter reject multiple/non-consecutive ones). Skipped when the query equals the
    last user message, so a single-intent turn adds nothing and the cached prefix holds.
    """
    task = (state.get("tasks") or [None])[0]
    query = str((task or {}).get("query") or "").strip()
    if not query:
        return base
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            if str(msg.content or "").strip() == query:
                return base
            break
    return SystemMessage(content=f"{base.content}\n\n{TASK_NOTE_PREAMBLE}{query}")


def ground_current_date(base: SystemMessage, tz: str | None = None) -> SystemMessage:
    """Append today's date and route relative-date resolution to the resolve_date tool.

    The note is appended last so the cacheable prefix does not shift each request.
    Computed per request, since the graph is built once and would otherwise serve a
    date frozen at boot. Invalid/None ``tz`` falls back to UTC.
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
        "correct it. If the traveller gave NO date and you are about to call a "
        "date-bound tool (a flight or hotel search, a booking, creating a trip with "
        "dates), you MUST ask which date they want — never fall back to "
        f"{today}. Never invent a date the traveller did not give. An undated "
        'day-by-day suggestion ("gợi ý lịch trình 3 ngày") needs no date: answer '
        "it as Day 1, Day 2, Day 3 without asking and without calendar dates. Ask, "
        "too, when resolve_date reports the expression is ambiguous."
    )
    return SystemMessage(content=f"{base.content}\n\n{note}")
