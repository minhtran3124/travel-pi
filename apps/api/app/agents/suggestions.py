"""Context-aware follow-up suggestion keys, keyed off the agent's current_flow.

Deterministic heuristic (MIN-55, phase 1): each sub-agent flow maps to a small,
curated set of follow-up suggestion *keys*. Keys are locale-agnostic stable
identifiers; the web client resolves them to localized chip labels/prompts via
its i18n catalog (apps/web/messages/*.json -> Chat.followups). Returns [] for an
unknown/None flow so the client renders no chips.

A future phase may swap this map for LLM-generated suggestions; keep the
`suggestions_for_flow` signature stable so callers (router + stream mapper) and
the response contract do not change.
"""

from __future__ import annotations

#: Max chips surfaced per turn (keep the UI uncluttered — MIN-55).
MAX_SUGGESTIONS = 3

_FLOW_SUGGESTIONS: dict[str, list[str]] = {
    "planner": ["planner.addDay", "planner.adjustBudget", "planner.findStay"],
    "concierge": [
        "concierge.nearbyPlaces",
        "concierge.checkWeather",
        "concierge.getThere",
    ],
    "journal": ["journal.addNote", "journal.viewTimeline", "journal.tripSummary"],
    "booking": ["booking.otherOptions", "booking.bookThis", "booking.comparePrices"],
    "budget": ["budget.addExpense", "budget.remaining", "budget.breakdown"],
}


def suggestions_for_flow(current_flow: str | None) -> list[str]:
    """Return up to MAX_SUGGESTIONS follow-up suggestion keys for a flow.

    :param current_flow: The sub-agent the supervisor last routed to
        (``planner|concierge|journal|budget|booking``) or ``None``.
    :return: A list of stable suggestion keys, or ``[]`` when the flow is
        unknown/``None``.
    """
    if not current_flow:
        return []
    return _FLOW_SUGGESTIONS.get(current_flow, [])[:MAX_SUGGESTIONS]
