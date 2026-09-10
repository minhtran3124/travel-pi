"""Supervisor routing node (specs/travel-agent Task 5.3).

Classifies the user's intent with structured output and emits an ordered task
list. A downstream conditional edge decides whether to route to the existing
static sub-agent nodes, the HITL plan node, or parallel synthesis workers via
``Send``. Unknown intent ends gracefully with a fallback message.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import BaseModel, Field, field_validator

from app.agents.constants import ALL_SUBAGENTS, MAX_LEDGER_STEPS
from app.agents.context import AgentContext
from app.agents.copy import system_reply
from app.agents.schemas import AgentTask
from app.agents.state import TravelAgentState, ground_current_date, system_with_summary
from app.core.dates import AmbiguousDateError, resolve_travel_date, today_in_timezone
from app.core.languages import DEFAULT_LANGUAGE, LANGUAGE_NAMES, SUPPORTED_LANGUAGES
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
    plan: list[_SecondaryTarget] | None = Field(
        default=None,
        description=(
            "Additional INDEPENDENT specialists whose slice does NOT depend on "
            "the primary's result; each runs in PARALLEL and sees only this "
            "message, never the primary's output. Never the primary agent, never "
            "'booking'. Omit any step that a single specialist can do itself — a "
            "chain that lives inside one specialist's toolset needs no plan. But "
            "never omit a step the primary has NO tool for: local tips, visas and "
            "general travel knowledge are concierge-only, so a trip-planning "
            "message that also asks for one of them is target_agent='planner' "
            "with plan=['concierge']. Weather and places are planner-owned and "
            "are not a reason to fan out. "
            "Leave null for the common single-intent case. Duplicate, invalid or "
            "nested steps are dropped or unwrapped in code; each entry is a "
            "bare specialist name. The only follow-on channel — there is no "
            "other way to queue an additional specialist this turn."
        ),
    )
    language: str = Field(
        default=DEFAULT_LANGUAGE,
        description=(
            "The traveller's PRIMARY/DOMINANT language across the whole "
            f"conversation (code, one of {'/'.join(SUPPORTED_LANGUAGES)}). Default "
            f"to {LANGUAGE_NAMES[DEFAULT_LANGUAGE]} ('{DEFAULT_LANGUAGE}') when the "
            "language is unclear or ambiguous. Ignore lone interjections and "
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

    @field_validator("plan", mode="before")
    @classmethod
    def _coerce_plan(cls, value: object) -> list[str] | None:
        """Degrade a malformed ``plan`` instead of raising a ValidationError.

        The model occasionally emits nested ``{"target_agent": ...}`` objects,
        an unknown or non-specialist name, or ``booking`` (never a valid
        follow-on). Rather than failing the whole routing decision, each entry
        is coerced to a bare specialist name or dropped with a WARNING; an empty
        result becomes ``None``. Declared as a ``before`` validator so the JSON
        schema sent to the model is unchanged (the four-name enum is preserved).
        """
        if value is None:
            return None
        if isinstance(value, (str, dict)):
            value = [value]
        elif not isinstance(value, list):
            logger.warning("[agent] supervisor dropping non-list plan: %r", value)
            return None
        valid = {"planner", "concierge", "journal", "budget"}
        coerced: list[str] = []
        for entry in value:
            if isinstance(entry, str) and entry in valid:
                coerced.append(entry)
            elif isinstance(entry, dict) and entry.get("target_agent") in valid:
                coerced.append(entry["target_agent"])
            else:
                logger.warning("[agent] supervisor dropping plan entry: %r", entry)
        return coerced or None


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
        # baseline on the first turn: the router keeps the default unless the traveller
        # clearly writes in another language, so an ambiguous/short opener stays
        # English instead of drifting.
        established = state.get("language") or DEFAULT_LANGUAGE
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
        # Detected language, resolved BEFORE the terminal branches below so a
        # code-authored reply (unknown intent / tier gate) is served in the
        # language of THIS turn, not the pre-turn default. The `or` fallback
        # fires only when the model returns a falsy/empty code — it does not pin
        # the language, so a genuine, model-reported switch still flows through
        # `intent.language`.
        lang = getattr(intent, "language", None) or state.get(
            "language", DEFAULT_LANGUAGE
        )
        if target not in SUBAGENTS:
            logger.info("[agent] supervisor → END (unknown intent: %s)", target)
            return Command(
                update={
                    "messages": [
                        AIMessage(content=system_reply("unknown_intent", lang))
                    ],
                    "language": lang,
                }
            )
        # Tier gate (D.1): if the resolved context restricts sub-agents and the
        # chosen target is not in the allow-list, degrade gracefully instead of
        # routing there.  This also blocks the plan->booking HITL path for free
        # users because "plan" is only reachable via this branch.
        if ctx.allowed_subagents is not None and target not in ctx.allowed_subagents:
            logger.info("[agent] supervisor → END (tier-gated: %s)", target)
            return Command(
                update={
                    "messages": [
                        AIMessage(content=system_reply("booking_upgrade", lang))
                    ],
                    "language": lang,
                }
            )
        # MIN-65 D3: normalize raw slots in code (never trust the LLM to resolve
        # a date/number itself).
        trip_facts = _normalize_slots(
            getattr(intent, "slots", None), today_in_timezone(ctx.timezone)
        )
        # GH-117 Path A: build the parallel task list. The primary intent is
        # task 0; each additional INDEPENDENT specialist becomes task 1, 2, etc.,
        # dispatched to a parallel ``synthesis_worker`` via ``Send``. Booking as a
        # target still produces one task so the routing edge can send it through
        # the HITL plan node, but booking is never queued as a follow-on task.
        # The supervisor may emit a ``plan`` of independent specialists to run
        # this turn alongside ``target``. The list is built in plain
        # Python and never trusts the model blindly: it is DEDUPLICATED (primary
        # first, then each follow-on in order, skipping any agent already queued —
        # no duplicate specialist workers, since each worker sees only this
        # message and a repeat would just do the same work twice), drops anything
        # unknown or "booking" (always HITL, never queued — defensive; the
        # ``_SecondaryTarget`` type already forbids it) or a tier-gated agent, and
        # caps the follow-ons at ``MAX_LEDGER_STEPS - 1``. A booking *target*
        # routes through the HITL plan node with no follow-ons.
        raw_plan = getattr(intent, "plan", None)
        candidates = list(raw_plan or [])
        task_agents: list[str] = [target]
        if target != "booking":
            for step in candidates:
                if len(task_agents) >= MAX_LEDGER_STEPS:
                    break
                if step not in ALL_SUBAGENTS or step == "booking":
                    continue
                if step in task_agents:  # dedupe primary + already-queued specialists
                    continue
                if (
                    ctx.allowed_subagents is not None
                    and step not in ctx.allowed_subagents
                ):
                    continue
                task_agents.append(step)
        # Use the last user message as the query for every task. Each worker
        # prompt narrows the focus to the specialist's domain.
        last_user_message = ""
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                last_user_message = str(msg.content or "")
                break
        tasks = [
            AgentTask(agent=agent, query=last_user_message, index=idx).model_dump()
            for idx, agent in enumerate(task_agents)
        ]
        logger.info("[agent] supervisor tasks=%d (intent=%s)", len(tasks), target)
        return Command(
            update={
                "current_flow": target,
                "language": lang,
                "trip_facts": trip_facts,
                "tasks": tasks,
            }
        )

    return supervisor
