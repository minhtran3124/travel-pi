"""Date resolution tool (specs/agent-date-resolution Task 2.1, 5.3).

The agent must never do date arithmetic in its head — a slip ("next Friday"
computed wrong) is invisible unless it's a tool call in the trace. This module
exposes a single read-only tool, ``resolve_date``, that resolves the
traveller's literal date expression in two stages: a zero-token numeric fast
path (:func:`app.core.dates.parse_numeric_date`) for ISO/day-month forms, and
— for anything worded (any language) — a structured-output LLM call
(``date_resolution``) that returns a *parsed intent*, never a computed date;
:func:`app.core.dates.compute_from_intent` then does the arithmetic in code.
The model is never trusted with the arithmetic, only with reading language.
The tool returns a summary the agent can restate verbatim to the traveller —
ISO date, weekday, and the grounded "today" — so the resolution is both
auditable in the tool trace and self-checkable by the human. Ambiguity is the
only path that should lead to a follow-up question; everything resolvable
resolves without one.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Annotated

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, ToolException, tool
from langgraph.runtime import get_runtime
from langgraph.types import Command
from pydantic import Field

from app.agents.context import AgentContext
from app.clients.llm import get_agent_llm
from app.core.config import get_settings
from app.core.dates import (
    AmbiguousDateError,
    compute_from_intent,
    parse_numeric_date,
    today_in_timezone,
)
from app.prompts.registry import registry
from app.schemas.date_intent import DateIntent
from app.tools._base import log_tool_call

logger = logging.getLogger(__name__)

#: Argument description for ``resolve_date``. Declared inline via ``Annotated``
#: rather than a hand-authored ``args_schema``: the tool takes an injected
#: ``InjectedToolCallId``, and an explicit schema that omits injected args
#: breaks LangGraph's ToolNode injection
#: (docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md).
_EXPRESSION_DESC = (
    "The traveller's date wording, exactly as they said it (e.g. "
    "'next Friday', 'ngày mai', 'thứ 6 tuần sau', '15/03', 'in 3 days'). "
    "Pass it through unchanged — do not compute or reformat a date "
    "yourself; this tool resolves it deterministically."
)


def _blocked_on_traveller(tool_call_id: str, message: str) -> Command:
    """Report a date that only the traveller can disambiguate (gh-109).

    Sets ``awaiting_user`` so ``dispatch_next`` abandons the rest of the turn's
    ledger, the same way the ``needs_clarification`` tool does. That tool was
    the *only* writer of the flag, so a model that asked for the missing date in
    prose instead of calling it left the flag false — and every queued sub-agent
    then re-answered the same question, producing one visibly duplicated reply.
    Keying the flag to a tool that *deterministically could not resolve a
    required fact* removes the dependency on the model choosing to call a tool.

    ``status="error"`` keeps the failure visible to the model, to the SSE
    ``tool_result`` event, and to the transient/logic tool-error split (MIN-49),
    exactly as the previous ``ToolException`` did.

    :param tool_call_id: The originating tool call id, injected by LangGraph.
    :param message: The failure text, naming the problem and instructing the
        model to ask the traveller (unchanged from the raising version).
    :return: A ``Command`` setting ``awaiting_user`` with the paired ``ToolMessage``.
    """
    logger.info("[agent] tool=resolve_date blocked on traveller: %s", message)
    return Command(
        update={
            "awaiting_user": True,
            "messages": [
                ToolMessage(content=message, tool_call_id=tool_call_id, status="error")
            ],
        }
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


def _parse_via_llm(expression: str, today: date, tz_name: str) -> DateIntent:
    """Ask the ``date_resolution`` model to parse ``expression`` into a :class:`DateIntent`.

    The model never computes a date — it only reports the shape of what the
    traveller meant; :func:`app.core.dates.compute_from_intent` does the
    arithmetic. Any provider/validation failure becomes a :class:`ToolException`
    rather than escaping and killing the agent turn.

    :param expression: The traveller's literal date wording.
    :param today: The current date in the traveller's timezone, interpolated
        into the system prompt so the model grounds relative language.
    :param tz_name: The IANA zone "today" is grounded in, also interpolated.
    :return: The model's parsed intent.
    :raises ToolException: If the model/provider call fails or does not
        return a usable intent.
    """
    system_prompt = (
        registry.get("date_resolution")
        .replace("{{TODAY_DATE}}", today.isoformat())
        .replace("{{TODAY_WEEKDAY}}", today.strftime("%A"))
        .replace("{{TIMEZONE}}", tz_name)
    )
    llm = get_agent_llm("date_resolution")
    parser = llm.with_structured_output(DateIntent, method="function_calling")
    try:
        return parser.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=expression)]
        )
    except Exception as e:  # noqa: BLE001 - provider boundary, must never crash the turn
        raise ToolException(
            f"could not resolve {expression!r}: {e}. Ask the traveller for a "
            "concrete date."
        ) from e


@tool
def resolve_date(
    expression: Annotated[str, Field(description=_EXPRESSION_DESC)],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> str | Command:
    """Resolve a relative/weekday/partial date expression to a concrete date.

    Call this for ANY date the traveller gives you that is not already plain
    ISO ``YYYY-MM-DD`` — relative words, weekday names, "next weekend", day
    offsets, or a day/month with no year. Never do this arithmetic yourself,
    in any language. Pass the traveller's wording through exactly as said.
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
    :return: On failure, a ``Command`` setting ``awaiting_user`` (see
        :func:`_blocked_on_traveller`) — ``expression`` is ambiguous, names a
        calendar date that has already passed, or is otherwise invalid. The
        only path that should lead to a question.
    """
    log_tool_call("resolve_date", {"expression": expression})
    tz_name = _grounding_timezone()
    today = today_in_timezone(tz_name)
    try:
        # Zero-token fast path: numeric/ISO forms never need a model call.
        iso = parse_numeric_date(expression, today)
    except AmbiguousDateError:
        # Not numeric — hand the wording to the parser LLM, then compute the
        # date in code from its structured intent.
        intent = _parse_via_llm(expression, today, tz_name)
        try:
            iso = compute_from_intent(intent, today)
        except AmbiguousDateError as e:
            return _blocked_on_traveller(
                tool_call_id,
                f"{expression!r} is ambiguous: {e}. Do not guess — ask the "
                "traveller for a concrete date (an exact day, or a clearer "
                "relative/weekday phrase).",
            )
        except (OverflowError, OSError, ValueError) as e:
            return _blocked_on_traveller(
                tool_call_id,
                f"{expression!r} is not a valid date ({e}). Ask the traveller "
                "for a concrete date.",
            )
    except (OverflowError, OSError, ValueError) as e:
        return _blocked_on_traveller(
            tool_call_id,
            f"{expression!r} is not a valid date ({e}). Ask the traveller for a "
            "concrete date.",
        )
    resolved = datetime.strptime(iso, "%Y-%m-%d").date()
    # 1-day grace for timezone skew, mirroring the guard in flight/hotel tools:
    # `today` is grounded here, but a traveller a zone behind may say "today"
    # for what is, by this clock, yesterday.
    if resolved < today - timedelta(days=1):
        return _blocked_on_traveller(
            tool_call_id,
            f"{expression!r} resolved to {iso}, which is in the past (today is "
            f"{today.isoformat()}). Do not guess — ask the traveller which "
            "upcoming date they mean.",
        )
    return (
        f"{iso} — {resolved.strftime('%A')}, {resolved.strftime('%-d %B %Y')}. "
        f"Today is {today.isoformat()} ({tz_name})."
    )


DATE_TOOLS = [resolve_date]


def resolve_date_over_mcp(expression: str) -> str:
    """MCP-servable ``resolve_date``: same resolution, no agent control flow.

    Adding the ``InjectedToolCallId`` parameter to :func:`resolve_date` made
    ``build_mcp_server`` skip it — that skip is correct in general (an external
    client has no LangGraph tool-call id to supply), but it silently dropped a
    read-only date tool that MCP clients could previously list and call, while
    ``/agent/manifest`` kept advertising it (PR #114 review).

    Delegating to ``resolve_date.func`` keeps one implementation of the
    resolution rules. The only difference is how "the traveller must
    disambiguate this" is reported: the agent path returns a ``Command`` that
    sets ``awaiting_user``, which is meaningless off-graph, so here the same
    message is raised as a ``ToolException`` the MCP client sees as an error.

    :param expression: The traveller's literal date wording, unmodified.
    :return: The resolved-date summary, identical to the agent path's.
    :raises ToolException: When the expression is ambiguous, invalid, or past —
        carrying the same text the agent would have put in its ``ToolMessage``.
    """
    result = resolve_date.func(expression=expression, tool_call_id="mcp")
    if isinstance(result, Command):
        # _blocked_on_traveller packs the text into the paired ToolMessage.
        raise ToolException(result.update["messages"][0].content)
    return result
