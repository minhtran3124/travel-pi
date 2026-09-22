"""Per-run research context — LangGraph ``context`` channel for the deep agent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchContext:
    """Resolved per-run identity read by the store-namespace factories and grader."""

    user_id: str
    trip_id: str
    run_id: str
    language: str
    timezone: str
    #: The traveller's stated departure point for this turn; ``None`` on revise /
    #: resume turns, whose thread already carries it. Never inferred.
    origin: str | None = None
