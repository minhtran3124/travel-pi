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

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage
from langgraph.store.base import BaseStore

from app.agents.copy import system_reply
from app.agents.state import TravelAgentState
from app.core.config import get_settings
from app.exceptions import AppError, ConflictError, RateLimitError

if TYPE_CHECKING:  # keep the research package (and deepagents) off the import path
    from app.research.service import ResearchService

logger = logging.getLogger(__name__)

#: Factory the node calls to obtain a ready service; kept as a factory so the node
#: never captures a request session and tests can inject a stub.
ResearchServiceFactory = Callable[[], "ResearchService"]

#: Strong references to in-flight research drivers. The chat node schedules the run
#: with ``asyncio.create_task`` and returns immediately; without a live reference the
#: event loop may garbage-collect the task mid-run, so it is parked here until done.
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _schedule(coro: Coroutine[Any, Any, None]) -> None:
    """Run ``coro`` as a background task off the current turn, holding a strong
    reference until it completes so the loop cannot collect it mid-flight. The node
    runs on the event loop (an async graph node), so ``create_task`` is valid here."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


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


#: ``ResearchService.chat_state`` value → the status copy the chat replies with.
_STATUS_COPY: dict[str, str] = {
    "running": "research_in_progress",
    "completed": "research_completed",
    "needs_review": "research_needs_review",
}


def _research_status(
    run_state: str,
    language: str | None,
    summary: str | None = None,
) -> dict:
    """The existing-run reply, followed by the dossier's traveller summary when one
    exists; ``research_status`` makes it terminal for ``reflection`` just like the
    launch flag."""
    copy = system_reply(_STATUS_COPY[run_state], language)
    return {
        "current_flow": "research",
        "messages": [
            AIMessage(
                content=f"{copy}\n\n{summary}" if summary else copy,
                additional_kwargs={"research_status": run_state},
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

    def _unavailable(language: str | None) -> dict:
        return {
            "messages": [
                AIMessage(content=system_reply("research_unavailable", language))
            ]
        }

    async def research(state: TravelAgentState) -> dict:
        language = state.get("language")
        # Kill switch (design §12.2): the whole feature is off during rollout, so
        # the launcher declines instead of booking a run.
        if not get_settings().research_enabled:
            return _unavailable(language)
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
        service = service_factory()
        # No built agent (flag on but the build failed) means nothing can drive a
        # booked run. Decline without touching the DB rather than stranding a
        # ``running`` row that only the 30-min sweep would ever clear.
        if not service.runnable:
            return _unavailable(language)
        user_id = state.get("user_id")
        # A trip with a finished or live run gets its status, never a new run: the
        # chat passes no instruction, so a re-run would be an empty revise that
        # spends the daily cap. Revising goes through the Research tab.
        run_state = service.chat_state(user_id, trip_id)
        if run_state in _STATUS_COPY:
            summary = (
                service.completed_summary(user_id, trip_id)
                if run_state != "running"
                else None
            )
            return _research_status(run_state, language, summary)
        # Flights need a departure point and the trip holds none: ask, never assume.
        # The supervisor lifts the answer into ``trip_facts`` and routes it back here.
        origin = ((state.get("trip_facts") or {}).get("origin") or "").strip()
        if not origin:
            return {
                "current_flow": "research",
                "awaiting_user": True,
                "messages": [
                    AIMessage(content=system_reply("research_needs_origin", language))
                ],
            }
        try:
            run_id = service.start(user_id, trip_id)
        except ConflictError:
            # A run for this trip is already in flight (already being driven): reassure
            # with the same "started" copy rather than surfacing a 500, and do not
            # schedule a second driver for the same thread.
            return _research_started(language)
        except RateLimitError:
            # Over the daily cap shared with the REST start and revise: say so, rather
            # than the generic error copy that invites an immediate retry.
            return {
                "messages": [
                    AIMessage(content=system_reply("research_limit_reached", language))
                ]
            }
        except AppError:
            # Any other domain failure (e.g. the trip is not the caller's) becomes a
            # readable reply, never an unhandled 500 out of the graph.
            return {
                "messages": [
                    AIMessage(content=system_reply("agent_error_fallback", language))
                ]
            }
        # Book succeeded: drive the run off this turn. The node must NOT await it —
        # the chat reply returns now and the dossier streams into the Research tab.
        _schedule(
            service.launch(
                run_id,
                user_id,
                trip_id,
                language=language,
                origin=origin,
            )
        )
        return _research_started(language)

    return research


def build_research_service(store: BaseStore | None):
    """Build a ``ResearchService`` on the shared session factory for the chat node.

    The service manages its own sessions (never a request session, design §5). The
    agent and bus come from the process-level runtime holder that lifespan populated
    (``app/research/runtime.py``), so the chat node drives the **same** compiled
    agent and progress bus as the REST routes. When research is off or the build
    failed the holder yields ``(None, None)`` and ``service.runnable`` is ``False``,
    so the node declines instead of booking an unrunnable row.
    """
    from app.db.engine import get_session_factory
    from app.research.runtime import get_research_runtime
    from app.research.service import ResearchService

    agent, bus = get_research_runtime()
    return ResearchService(
        session_factory=get_session_factory(get_settings().database_url),
        store=store,
        agent=agent,
        bus=bus,
    )
