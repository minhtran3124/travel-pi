"""Chat-graph entry into the trip-research deep agent (design §6).

The ``research`` node is a specialist-shaped graph node that makes **no** LLM call:
the supervisor has already classified the intent. It books a background research
run through :class:`app.research.service.ResearchService` and replies with
code-authored copy, so the run is driven entirely off the chat graph — the chat
turn never blocks on it.

The node is registered under the name ``"research"`` so the existing
``for name in SUBAGENTS`` wiring and ``reflection``'s ``destinations`` cover it
with no hand-written edges (design §12.1).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage
from langgraph.store.base import BaseStore

from app.agents.copy import system_reply
from app.agents.state import TravelAgentState
from app.core.config import get_settings
from app.exceptions import AppError, ConflictError

if TYPE_CHECKING:  # keep the research package (and deepagents) off the import path
    from app.research.service import ResearchService

#: Factory the node calls to obtain a ready service; kept as a factory so the node
#: never captures a request session and tests can inject a stub.
ResearchServiceFactory = Callable[[], "ResearchService"]


def _research_started(language: str | None) -> dict:
    """The launched-run reply: the guard flag on the ``AIMessage`` lets
    ``reflection`` end the turn so a REVISE can never start a second job."""
    return {
        "current_flow": "research",
        "messages": [
            AIMessage(
                content=system_reply("research_started", language),
                additional_kwargs={"research_started": True},
            )
        ],
    }


def make_research_node(service_factory: ResearchServiceFactory):
    """Return the ``research`` node bound to a service factory (design §6).

    :param service_factory: Zero-arg callable returning a ``ResearchService``;
        invoked only on the launch path, never when the flag is off or no trip is
        active, so the flag-off and no-trip replies stay free of DB work.
    :return: A node function ``research(state) -> dict``.
    """

    def research(state: TravelAgentState) -> dict:
        language = state.get("language")
        # Kill switch (design §12.2): the whole feature is off during rollout, so
        # the launcher declines instead of booking a run.
        if not get_settings().research_enabled:
            return {
                "messages": [
                    AIMessage(content=system_reply("research_unavailable", language))
                ]
            }
        trip_id = state.get("trip_id")
        # Deep research digs into one concrete trip; without one, ask the traveller
        # which trip they mean (awaiting_user ends the turn via reflection's guard).
        if not trip_id:
            return {
                "awaiting_user": True,
                "messages": [
                    AIMessage(content=system_reply("research_needs_trip", language))
                ],
            }
        try:
            service_factory().start(state.get("user_id"), trip_id)
        except ConflictError:
            # A run for this trip is already in flight: reassure with the same
            # "started" copy ("...follow along in the Research tab") rather than
            # surfacing a 500 — the dossier the traveller wants is already coming.
            return _research_started(language)
        except AppError:
            # Any other domain failure (e.g. the trip is not the caller's) becomes a
            # readable reply, never an unhandled 500 out of the graph.
            return {
                "messages": [
                    AIMessage(content=system_reply("agent_error_fallback", language))
                ]
            }
        return _research_started(language)

    return research


def build_research_service(store: BaseStore | None):
    """Build a ``ResearchService`` on the shared session factory for the chat node.

    The service manages its own sessions (never a request session, design §5);
    ``start`` — all the launcher needs — touches only the DB, so the agent/bus are
    left unbuilt here and the background runner is driven from the research surface.
    """
    from app.db.engine import get_session_factory
    from app.research.progress import ProgressBus
    from app.research.service import ResearchService

    return ResearchService(
        session_factory=get_session_factory(get_settings().database_url),
        store=store,
        agent=None,
        bus=ProgressBus(),
    )
