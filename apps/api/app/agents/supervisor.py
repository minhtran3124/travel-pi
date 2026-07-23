"""Supervisor routing node (specs/travel-agent Task 5.3).

Classifies the user's intent with structured output and hands off to one
specialist sub-agent via ``Command(goto=...)`` — the inter-agent routing seam.
Unknown intent ends gracefully with a fallback message.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.agents.constants import ALL_SUBAGENTS, BOOKING_UPGRADE_MSG, MAX_LEDGER_STEPS
from app.agents.context import AgentContext
from app.agents.state import TravelAgentState, ground_current_date, system_with_summary
from app.core.dates import AmbiguousDateError, resolve_travel_date, today_in_timezone
from app.prompts.registry import registry

# Re-exported for callers that do `from app.agents.supervisor import SUBAGENTS`.
# Single source of truth lives in context.py (avoids circular imports).
SUBAGENTS = ALL_SUBAGENTS
_Target = Literal["planner", "concierge", "journal", "booking", "budget"]
# Secondary intent can never be "booking" (HLD non-goal — booking always needs
# the HITL plan-approval path, never a queued follow-on); MIN-65 DESIGN D3.
_SecondaryTarget = Literal["planner", "concierge", "journal", "budget"]

logger = logging.getLogger(__name__)


class ExtractedSlots(BaseModel):
    """Raw traveller-stated mentions for this turn — verbatim text only.

    The model extracts what was said, never a resolved value (MIN-65 DESIGN
    D3, the "LLM parses, code computes" pattern): dates stay as free text
    ("next Friday", "15/8") and are turned into ISO dates by
    :func:`app.core.dates.resolve_travel_date` in plain Python after the LLM
    call returns, never by the model itself. Every field is optional so the
    model is never pressured to invent a value it wasn't given.
    """

    destination: str | None = None
    origin: str | None = None
    start_date_text: str | None = None
    end_date_text: str | None = None
    adults: int | None = None
    children: int | None = None
    rooms: int | None = None
    budget_text: str | None = None
    cabin_class: str | None = None
    hotel_area: str | None = None


class SupervisorIntent(BaseModel):
    """Structured routing decision."""

    target_agent: _Target = Field(description="Which specialist should handle this.")
    secondary_agent: _SecondaryTarget | None = Field(
        default=None,
        description=(
            "A second, clearly distinct sub-agent to queue for this turn, only "
            "when the traveller's message contains two separate requests (e.g. "
            "both a flight and a hotel need). Never 'booking', and never the "
            "same value as target_agent. Leave null for the common single-intent "
            "case. Superseded by `plan` when that is set."
        ),
    )
    plan: list[_SecondaryTarget] | None = Field(
        default=None,
        description=(
            "An ORDERED list of follow-on sub-agents to run this turn AFTER "
            "target_agent, for a request that spans several specialists (e.g. "
            "'plan my Tokyo weekend: flights + weather + itinerary' → "
            "target_agent=planner, plan=[concierge, planner]). List only the "
            "follow-ons, in execution order. A specialist MAY recur when it does "
            "distinct work at a later stage. Never 'booking'. Leave null for a "
            "single-domain request (then target_agent alone handles it). Extra "
            "or invalid steps are dropped in code."
        ),
    )
    language: str = Field(
        default="en",
        description=(
            "The traveller's PRIMARY/DOMINANT language across the whole "
            "conversation (code, e.g. 'en'/'vi'). Default to English ('en') when "
            "the language is unclear or ambiguous. Ignore lone interjections and "
            "loanwords ('ok','fine','good'); only report a different code on a "
            "clear, sustained switch."
        ),
    )
    slots: ExtractedSlots | None = Field(
        default=None,
        description=(
            "Trip details the traveller explicitly stated THIS turn, verbatim. "
            "Leave every field null if not mentioned or you are unsure — never "
            "guess or infer a value."
        ),
    )


# Loose "number + currency hint" match: a digit run (with optional , / . group
# separators) followed by an optional unit token. Deliberately simple — MIN-65
# DESIGN D3 keeps budget normalization to "parse or drop", not a full currency
# parser; a raw mention that doesn't match is dropped rather than guessed.
_BUDGET_RE = re.compile(
    r"(?P<amount>\d[\d.,]*)\s*(?P<unit>triệu|tr|ngh\xecn|ng\xe0n|k|usd|vnd|đ|\$|₫)?",
    re.IGNORECASE,
)


def _normalize_date_slot(raw: str | None, today: date) -> str | None:
    """Resolve a raw date mention to ISO, or drop it — never guess.

    :param raw: Verbatim date text from :class:`ExtractedSlots`, or None.
    :param today: "Today" in the traveller's timezone, anchoring a missing year.
    :return: An ISO ``YYYY-MM-DD`` date, or None if absent/unresolvable.
    """
    if not raw or not raw.strip():
        return None
    try:
        return resolve_travel_date(raw, today)
    except (AmbiguousDateError, ValueError):
        return None


def _normalize_count_slot(value: int | None) -> int | None:
    """Keep a positive headcount/room count; drop zero, negative, or absent.

    :param value: Raw int from :class:`ExtractedSlots`, or None.
    :return: ``value`` if a positive int, else None.
    """
    if value is None or value <= 0:
        return None
    return value


def _normalize_children_slot(value: int | None) -> int | None:
    """Keep a non-negative children count, including zero — unlike adults/
    rooms, zero is a meaningful, commonly-stated value ("no kids") and is a
    required field on the hotel search tools ("0 if none"). Only drop a
    genuinely negative or absent value.

    :param value: Raw int from :class:`ExtractedSlots`, or None.
    :return: ``value`` if 0 or a positive int, else None.
    """
    if value is None or value < 0:
        return None
    return value


def _normalize_budget_slot(raw: str | None) -> str | None:
    """Extract a number + optional currency hint from free text, or drop it.

    :param raw: Verbatim budget text from :class:`ExtractedSlots`, or None.
    :return: The matched "amount unit" text, or None if no number was found.
    """
    if not raw or not raw.strip():
        return None
    match = _BUDGET_RE.search(raw)
    if not match:
        return None
    amount = match.group("amount")
    unit = (match.group("unit") or "").strip()
    return f"{amount} {unit}".strip()


def _normalize_slots(slots: ExtractedSlots | None, today: date) -> dict:
    """Turn raw :class:`ExtractedSlots` into the ``trip_facts`` update dict.

    Only successfully-resolved keys are included — never an explicit ``None``
    for a slot that failed or wasn't mentioned, since ``merge_trip_facts``
    treats an absent key as "no update this turn", not "delete" (MIN-65
    DESIGN D1); explicitly passing None would be indistinguishable to the
    reducer but is avoided here for clarity at the call site.

    :param slots: The model's raw extraction for this turn, or None.
    :param today: "Today" in the traveller's timezone, for date resolution.
    :return: A dict of only the resolved slot values, keyed by trip-fact name.
    """
    if slots is None:
        return {}
    normalized: dict[str, str | int] = {}
    if slots.destination:
        normalized["destination"] = slots.destination
    if slots.origin:
        normalized["origin"] = slots.origin
    start_date = _normalize_date_slot(slots.start_date_text, today)
    if start_date:
        normalized["start_date"] = start_date
    end_date = _normalize_date_slot(slots.end_date_text, today)
    if end_date:
        normalized["end_date"] = end_date
    adults = _normalize_count_slot(slots.adults)
    if adults:
        normalized["adults"] = adults
    children = _normalize_children_slot(slots.children)
    if children is not None:
        normalized["children"] = children
    rooms = _normalize_count_slot(slots.rooms)
    if rooms:
        normalized["rooms"] = rooms
    budget = _normalize_budget_slot(slots.budget_text)
    if budget:
        normalized["budget"] = budget
    if slots.cabin_class:
        normalized["cabin_class"] = slots.cabin_class
    if slots.hotel_area:
        normalized["hotel_area"] = slots.hotel_area
    return normalized


def make_supervisor(llm: BaseChatModel):
    """Return the supervisor node bound to a routing LLM.

    :param llm: Chat model used for structured intent classification.
    :return: The ``supervisor`` node function.
    """
    # method="function_calling" avoids OpenAI's native json_schema parse path,
    # whose ParsedChatCompletion.parsed field trips a benign Pydantic serializer
    # warning when langchain-openai model_dump()s the response.
    router = llm.with_structured_output(SupervisorIntent, method="function_calling")
    system = SystemMessage(content=registry.get("supervisor"))

    def supervisor(state: TravelAgentState, runtime: Runtime[AgentContext]) -> Command:
        logger.info("[agent] node=supervisor")
        ctx = (
            runtime.context
            if runtime is not None and runtime.context is not None
            else AgentContext()
        )
        # Feed the already-established conversation language into the router so the
        # model itself returns the sticky value and does not flip on a lone English
        # interjection in an otherwise Vietnamese thread. English is the default
        # baseline on the first turn: the router keeps "en" unless the traveller
        # clearly writes in another language, so an ambiguous/short opener stays
        # English instead of drifting.
        established = state.get("language") or "en"
        base = SystemMessage(
            content=(
                f"{system.content}\n\n"
                f"Established conversation language: {established}; "
                "keep it unless the traveller clearly switches."
            )
        )
        intent = router.invoke(
            [
                system_with_summary(state, ground_current_date(base, ctx.timezone)),
                *state["messages"],
            ]
        )
        target = getattr(intent, "target_agent", None)
        if target not in SUBAGENTS:
            logger.info("[agent] supervisor → END (unknown intent: %s)", target)
            return Command(
                update={
                    "messages": [
                        AIMessage(content="I'm not sure how to help with that yet.")
                    ]
                },
                goto=END,
            )
        # Tier gate (D.1): if the resolved context restricts sub-agents and the
        # chosen target is not in the allow-list, degrade gracefully instead of
        # routing there.  This also blocks the plan->booking HITL path for free
        # users because "plan" is only reachable via this branch.
        if ctx.allowed_subagents is not None and target not in ctx.allowed_subagents:
            logger.info("[agent] supervisor → END (tier-gated: %s)", target)
            return Command(
                update={"messages": [AIMessage(content=BOOKING_UPGRADE_MSG)]},
                goto=END,
            )
        # Route booking through the HITL plan-approval node first.
        next_node = "plan" if target == "booking" else target
        logger.info("[agent] supervisor → %s (intent=%s)", next_node, target)
        # Persist the detected language. The `or` fallback fires only when the model
        # returns a falsy/empty code — it does not pin the language, so a genuine,
        # model-reported switch still flows through `intent.language`.
        lang = getattr(intent, "language", None) or state.get("language", "en")
        # MIN-65 D3: normalize raw slots in code (never trust the LLM to resolve
        # a date/number itself).
        trip_facts = _normalize_slots(
            getattr(intent, "slots", None), today_in_timezone(ctx.timezone)
        )
        # P1 task ledger: the supervisor may emit an ordered ``plan`` of follow-on
        # sub-agents to run this turn after ``target``; fall back to the legacy
        # single ``secondary_agent`` when ``plan`` is absent. An ordered plan is
        # honoured as written — a specialist MAY legitimately recur (e.g. planner
        # searches flights early, then builds the itinerary later), so steps are
        # not deduplicated. The queue is still built in plain Python and never
        # trusts the model blindly: drop anything unknown or "booking" (always
        # HITL, never queued — defensive; the ``_SecondaryTarget`` type already
        # forbids it) or a tier-gated agent, and cap the follow-ons at
        # ``MAX_LEDGER_STEPS - 1``. A booking *target* routes through the HITL
        # plan node with no queued follow-ons (matches the pre-ledger behavior).
        raw_plan = getattr(intent, "plan", None)
        if raw_plan:
            candidates, drop_target_dup = list(raw_plan), False
        else:
            # Legacy single-secondary path: a secondary equal to the target was
            # always a no-op, so preserve that drop for exact backward compat.
            legacy = getattr(intent, "secondary_agent", None)
            candidates, drop_target_dup = ([legacy] if legacy else []), True
        pending_flows: list[str] = []
        if target != "booking":
            for step in candidates:
                if len(pending_flows) >= MAX_LEDGER_STEPS - 1:
                    break
                if step not in ALL_SUBAGENTS or step == "booking":
                    continue
                if drop_target_dup and step == target:
                    continue
                if (
                    ctx.allowed_subagents is not None
                    and step not in ctx.allowed_subagents
                ):
                    continue
                pending_flows.append(step)
        return Command(
            update={
                "current_flow": target,
                "language": lang,
                "trip_facts": trip_facts,
                "pending_flows": pending_flows,
            },
            goto=next_node,
        )

    return supervisor
