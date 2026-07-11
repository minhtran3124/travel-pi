"""Date resolution tool (specs/agent-date-resolution Task 2.1).

The agent must never do date arithmetic in its head — a slip ("next Friday"
computed wrong) is invisible unless it's a tool call in the trace. This module
exposes a single read-only tool, ``resolve_date``, that hands the traveller's
literal date expression to :func:`app.core.dates.resolve_travel_date` (the
deterministic resolver) and returns a summary the agent can restate verbatim
to the traveller — ISO date, weekday, and the grounded "today" — so the
resolution is both auditable in the tool trace and self-checkable by the
human. Ambiguity is the only path that should lead to a follow-up question;
everything resolvable resolves without one.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from langchain_core.tools import ToolException, tool
from langgraph.runtime import get_runtime
from pydantic import Field

from app.agents.context import AgentContext
from app.core.config import get_settings
from app.core.dates import AmbiguousDateError, resolve_travel_date, today_in_timezone
from app.schemas.base import AppBaseModel
from app.tools._base import log_tool_call


class ResolveDateArgs(AppBaseModel):
    expression: str = Field(
        ...,
        description=(
            "The traveller's date wording, exactly as they said it (e.g. "
            "'next Friday', 'ngày mai', 'thứ 6 tuần sau', '15/03', 'in 3 days'). "
            "Pass it through unchanged — do not compute or reformat a date "
            "yourself; this tool resolves it deterministically."
        ),
    )


def _grounding_timezone() -> str:
    """Resolve the IANA zone to ground "today" on.

    Prefers the per-request traveller timezone carried on ``AgentContext``
    (``runtime.context.timezone``) — the system prompt grounds "today" on
    this same value (see ``ground_current_date`` in the supervisor/subagent
    system prompts), so the tool must agree with the prompt or it silently
    resolves relative dates a day off for a traveller outside the server's
    configured zone. Falls back to the global ``agent_timezone`` setting when
    there is no active graph runtime (e.g. called directly in a unit test or
    over MCP) or the context carries no timezone.

    :return: The IANA timezone name to ground "today" on.
    """
    try:
        runtime = get_runtime(AgentContext)
    except RuntimeError:
        return get_settings().agent_timezone
    ctx = runtime.context if runtime is not None else None
    if ctx is not None and ctx.timezone:
        return ctx.timezone
    return get_settings().agent_timezone


@tool(args_schema=ResolveDateArgs)
def resolve_date(expression: str) -> str:
    """Resolve a relative/weekday/partial date expression to a concrete date.

    Call this for ANY date the traveller gives you that is not already plain
    ISO ``YYYY-MM-DD`` — relative words, weekday names, "next weekend", day
    offsets, or a day/month with no year. Never do this arithmetic yourself.
    State the returned date back to the traveller so they can correct it — but
    say it in THEIR language and date format ("thứ Sáu 17/07/2026"), never by
    copying this tool's English wording into a reply written in another
    language. Only ask a follow-up question if this tool reports the expression
    is ambiguous, or the traveller gave no date signal at all.

    :param expression: The traveller's literal date wording, unmodified.
    :return: A summary carrying the resolved ISO date, its weekday spelled
        out with the full month name (so a day-first "DD/MM" reading can't be
        mistaken for the ISO date echoed back), and the grounded "today",
        e.g. ``"2026-04-03 — Friday, 3 April 2026. Today is 2026-07-11
        (Asia/Ho_Chi_Minh)."``
    :raises ToolException: If ``expression`` is ambiguous, names a calendar
        date that has already passed, or is otherwise invalid — names the
        problem and instructs asking the traveller for a concrete upcoming
        date. The only path that should lead to a question.
    """
    log_tool_call("resolve_date", locals())
    tz_name = _grounding_timezone()
    today = today_in_timezone(tz_name)
    try:
        iso = resolve_travel_date(expression, today)
    except AmbiguousDateError as e:
        raise ToolException(
            f"{expression!r} is ambiguous: {e}. Do not guess — ask the traveller "
            "for a concrete date (an exact day, or a clearer relative/weekday "
            "phrase)."
        ) from e
    except (OverflowError, OSError, ValueError) as e:
        raise ToolException(
            f"{expression!r} is not a valid date ({e}). Ask the traveller for a "
            "concrete date."
        ) from e
    resolved = datetime.strptime(iso, "%Y-%m-%d").date()
    # 1-day grace for timezone skew, mirroring the guard in flight/hotel tools:
    # `today` is grounded here, but a traveller a zone behind may say "today"
    # for what is, by this clock, yesterday.
    if resolved < today - timedelta(days=1):
        raise ToolException(
            f"{expression!r} resolved to {iso}, which is in the past (today is "
            f"{today.isoformat()}). Do not guess — ask the traveller which "
            "upcoming date they mean."
        )
    return (
        f"{iso} — {resolved.strftime('%A')}, {resolved.strftime('%-d %B %Y')}. "
        f"Today is {today.isoformat()} ({tz_name})."
    )


DATE_TOOLS = [resolve_date]
