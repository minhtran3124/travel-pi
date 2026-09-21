"""Trip-research agent surface (design §5) — JWT + premium, additive, flag-gated.

Thin router: validation, then :class:`ResearchService` (ownership, run bookkeeping,
dossier access), then domain-exception → HTTP mapping. Every route sits under
``CurrentUserDep`` and ``require_premium``; the module is only wired into the app
when ``settings.research_enabled`` is true (``app/main.py``), so with the flag off
every path is a clean 404. The SSE endpoint tails the in-process progress bus when
it holds the run, else builds a snapshot from the run row + store file index and
re-polls until the run reaches a terminal status.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.guardrails import redact_pii
from app.core.auth import CurrentUserDep, require_premium
from app.core.config import get_settings
from app.core.streaming import sse_response
from app.db.models.agent_run import AgentRun
from app.db.session import get_session
from app.exceptions import ForbiddenError, NotFoundError
from app.research.context import ResearchContext
from app.research.progress import ProgressBus
from app.research.runner import run_trip_research
from app.research.service import (
    RESEARCH_KIND,
    ResearchService,
)
from app.routers.tags import Tags
from app.schemas.error import ErrorResponse, error_responses
from app.schemas.research import (
    ResearchFileContent,
    ResearchFileWrite,
    ResearchStartRequest,
    ResearchStartResponse,
    ResearchStatusResponse,
)
from app.streaming.research_events import (
    ResearchDone,
    ResearchError,
    ResearchPhase,
    ResearchStart,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=[Tags.agent], responses=error_responses(422))

SessionDep = Annotated[Session, Depends(get_session)]

_DEFAULT_LANGUAGE = "en"
_PROPOSAL_KEY = "/proposal.json"
_TERMINAL = frozenset({"completed", "failed", "interrupted"})
_UNAVAILABLE = "Trip research is temporarily unavailable."

# 429/503 are outside error_responses()'s supported set, so declare them inline.
# Both booking routes spend the daily cap, enforced in ``ResearchService.start``.
_RATE_LIMITED = {429: {"model": ErrorResponse, "description": "Daily research limit"}}
_UNAVAILABLE_RESP = {503: {"model": ErrorResponse, "description": _UNAVAILABLE}}


# -- shared state dependencies ------------------------------------------------


def get_research_agent(request: Request) -> Any:
    """The lifespan-built research agent, or 503 when it is unavailable (design
    §12.2: a build failure leaves ``app.state.research_agent`` None)."""
    agent = getattr(request.app.state, "research_agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE)
    return agent


def get_research_bus(request: Request) -> ProgressBus:
    bus = getattr(request.app.state, "research_bus", None)
    if bus is None:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE)
    return bus


ResearchAgentDep = Annotated[Any, Depends(get_research_agent)]
ResearchBusDep = Annotated[ProgressBus, Depends(get_research_bus)]


def _isolated_factory(session: Session) -> sessionmaker[Session]:
    """A sessionmaker on the request session's engine, for background work and the
    service (which never reuses a request session); bind to the engine, not
    ``str(URL)`` which masks the password and breaks Postgres auth."""
    return sessionmaker(bind=session.get_bind(), expire_on_commit=False, future=True)


def get_research_service(
    agent: ResearchAgentDep,
    bus: ResearchBusDep,
    session: SessionDep,
) -> ResearchService:
    return ResearchService(
        session_factory=_isolated_factory(session),
        store=agent.store,
        agent=agent,
        bus=bus,
    )


ResearchServiceDep = Annotated[ResearchService, Depends(get_research_service)]


# -- helpers ------------------------------------------------------------------

_RUN_ID = Annotated[str, Path(description="Research run id")]
_TRIP_ID = Annotated[str, Path(description="Trip id")]
_FILE_PATH = Annotated[str, Path(description="Route-prefixed dossier path")]


def _namespace(user_id: str, trip_id: str) -> tuple[str, ...]:
    """Dossier store namespace (mirrors ``ResearchService._file_backend``)."""
    return ("users", user_id, RESEARCH_KIND, trip_id)


def _file_index(store: Any, user_id: str, trip_id: str) -> list[str]:
    try:
        items = store.search(_namespace(user_id, trip_id))
        return sorted(item.key for item in items)
    except Exception:  # noqa: BLE001 — a store read must never fail a status read
        return []


def _proposal_ready(store: Any, user_id: str, trip_id: str) -> bool:
    try:
        return store.get(_namespace(user_id, trip_id), _PROPOSAL_KEY) is not None
    except Exception:  # noqa: BLE001
        return False


def _thread_turn(
    factory: sessionmaker[Session],
    trip_id: str | None,
    *,
    upto: str | None = None,
) -> int:
    """Ordinal of a research run on its trip's dossier thread (1-based)."""
    if trip_id is None:
        return 1
    stmt = (
        select(func.count())
        .select_from(AgentRun)
        .where(AgentRun.trip_id == trip_id, AgentRun.kind == RESEARCH_KIND)
    )
    if upto is not None:
        stmt = stmt.where(AgentRun.created_at <= upto)
    with factory() as s:
        return int(s.scalar(stmt) or 0)


def _owned_run(service: ResearchService, run_id: str, user_id: str) -> AgentRun:
    """The caller's run, or 404 — a foreign run is indistinguishable from missing."""
    run = service.status(run_id)
    if run is None or run.user_id != user_id:
        raise NotFoundError("Research run not found")
    return run


def _status_body(
    run: AgentRun,
    store: Any,
    factory: sessionmaker[Session],
) -> ResearchStatusResponse:
    return ResearchStatusResponse(
        run_id=run.id,
        trip_id=run.trip_id,
        status=run.status,
        thread_turn=_thread_turn(factory, run.trip_id, upto=run.created_at),
        files=_file_index(store, run.user_id, run.trip_id),
        proposal_ready=_proposal_ready(store, run.user_id, run.trip_id),
    )


# -- routes -------------------------------------------------------------------


@router.post(
    "/trips/{trip_id}/research",
    response_model=ResearchStartResponse,
    status_code=202,
    summary="Start (or revise) in-depth research for a trip",
    dependencies=[Depends(require_premium)],
    responses={**error_responses(403, 409), **_RATE_LIMITED, **_UNAVAILABLE_RESP},
)
def start_research(
    trip_id: _TRIP_ID,
    body: ResearchStartRequest,
    auth_user: CurrentUserDep,
    service: ResearchServiceDep,
    agent: ResearchAgentDep,
    bus: ResearchBusDep,
    session: SessionDep,
    background: BackgroundTasks,
) -> ResearchStartResponse:
    """Book a run (ConflictError → 409 if one is already running), schedule the
    background runner, and return the run id + its turn. A trip that is not the
    caller's is a 403 (ownership is indistinguishable from absence in the store)."""
    try:
        run_id = service.start(auth_user.id, trip_id, body.instruction)
    except NotFoundError as exc:
        raise ForbiddenError("This trip is not available for research.") from exc

    factory = _isolated_factory(session)
    ctx = ResearchContext(
        user_id=auth_user.id,
        trip_id=trip_id,
        run_id=run_id,
        language=body.language or _DEFAULT_LANGUAGE,
        timezone=get_settings().agent_timezone,
    )
    background.add_task(
        run_trip_research,
        run_id=run_id,
        ctx=ctx,
        instruction=redact_pii(body.instruction) if body.instruction else None,
        agent=agent,
        bus=bus,
        session_factory=factory,
    )
    return ResearchStartResponse(
        run_id=run_id,
        thread_turn=_thread_turn(factory, trip_id),
    )


@router.post(
    "/research/{run_id}/revise",
    response_model=ResearchStartResponse,
    status_code=202,
    summary="Revise a trip's dossier as the next turn on its thread",
    dependencies=[Depends(require_premium)],
    responses={**error_responses(403, 404, 409), **_RATE_LIMITED},
)
def revise_research(
    run_id: _RUN_ID,
    body: ResearchStartRequest,
    auth_user: CurrentUserDep,
    service: ResearchServiceDep,
    agent: ResearchAgentDep,
    bus: ResearchBusDep,
    session: SessionDep,
    background: BackgroundTasks,
) -> ResearchStartResponse:
    """A revise is the next run on the same trip (same checkpointed thread), so it
    reuses the start path keyed off the prior run's trip."""
    prior = _owned_run(service, run_id, auth_user.id)
    try:
        new_run_id = service.start(auth_user.id, prior.trip_id, body.instruction)
    except NotFoundError as exc:
        raise ForbiddenError("This trip is not available for research.") from exc

    factory = _isolated_factory(session)
    ctx = ResearchContext(
        user_id=auth_user.id,
        trip_id=prior.trip_id,
        run_id=new_run_id,
        language=body.language or _DEFAULT_LANGUAGE,
        timezone=get_settings().agent_timezone,
    )
    background.add_task(
        run_trip_research,
        run_id=new_run_id,
        ctx=ctx,
        instruction=redact_pii(body.instruction) if body.instruction else None,
        agent=agent,
        bus=bus,
        session_factory=factory,
    )
    return ResearchStartResponse(
        run_id=new_run_id,
        thread_turn=_thread_turn(factory, prior.trip_id),
    )


@router.get(
    "/trips/{trip_id}/research",
    response_model=ResearchStatusResponse,
    summary="Latest research run for a trip",
    dependencies=[Depends(require_premium)],
    responses=error_responses(403, 404),
)
def latest_research(
    trip_id: _TRIP_ID,
    auth_user: CurrentUserDep,
    service: ResearchServiceDep,
    agent: ResearchAgentDep,
    session: SessionDep,
) -> ResearchStatusResponse:
    run = service.latest(trip_id)
    if run is None or run.user_id != auth_user.id:
        raise NotFoundError("No research run for this trip")
    return _status_body(run, agent.store, _isolated_factory(session))


@router.get(
    "/research/{run_id}",
    response_model=ResearchStatusResponse,
    summary="Research run status, dossier index and proposal flag",
    dependencies=[Depends(require_premium)],
    responses=error_responses(403, 404),
)
def research_status(
    run_id: _RUN_ID,
    auth_user: CurrentUserDep,
    service: ResearchServiceDep,
    agent: ResearchAgentDep,
    session: SessionDep,
) -> ResearchStatusResponse:
    run = _owned_run(service, run_id, auth_user.id)
    return _status_body(run, agent.store, _isolated_factory(session))


@router.get(
    "/research/{run_id}/files/{path:path}",
    response_model=ResearchFileContent,
    summary="Read one dossier file",
    dependencies=[Depends(require_premium)],
    responses=error_responses(403, 404),
)
def read_research_file(
    run_id: _RUN_ID,
    path: _FILE_PATH,
    auth_user: CurrentUserDep,
    service: ResearchServiceDep,
) -> ResearchFileContent:
    _owned_run(service, run_id, auth_user.id)
    content = service.file(run_id, path)
    if content is None:
        raise NotFoundError("Dossier file not found")
    return ResearchFileContent(path=path, content=content)


@router.put(
    "/research/{run_id}/files/{path:path}",
    response_model=ResearchFileContent,
    summary="Write (user-edit) one dossier file",
    dependencies=[Depends(require_premium)],
    responses=error_responses(403, 404),
)
def write_research_file(
    run_id: _RUN_ID,
    path: _FILE_PATH,
    body: ResearchFileWrite,
    auth_user: CurrentUserDep,
    service: ResearchServiceDep,
) -> ResearchFileContent:
    _owned_run(service, run_id, auth_user.id)
    # Normalise the addressed path the same way the store does, so the read-back path
    # matches what the backend keyed the write under.
    service.write_file(run_id, path, body.content)
    return ResearchFileContent(path=path, content=body.content)


@router.get(
    "/research/{run_id}/stream",
    summary="Live research progress as Server-Sent Events",
    dependencies=[Depends(require_premium)],
    responses=error_responses(403, 404),
)
def stream_research(
    run_id: _RUN_ID,
    auth_user: CurrentUserDep,
    service: ResearchServiceDep,
    agent: ResearchAgentDep,
    bus: ResearchBusDep,
):
    """Bus tail when the run is in-flight (replay + live), else a DB snapshot
    re-polled every 2 s until the run reaches a terminal status (design §4)."""
    run = _owned_run(service, run_id, auth_user.id)
    store = agent.store

    async def _events() -> AsyncIterator[Any]:
        if bus.has(run_id):
            async for event in bus.subscribe(run_id):
                yield event.to_sse()
                if isinstance(event, (ResearchDone, ResearchError)):
                    return
            # Falling out of that loop without a terminal event is possible: the
            # run can finish in the gap between ``has`` above and this generator's
            # first step (entering the loop suspends), in which case ``subscribe``
            # declines and yields nothing at all. Returning here would end the SSE
            # response with no terminal frame, and the client reads that as a run
            # that died. Fall through to the snapshot instead, so the stream always
            # terminates with a verdict regardless of how that race lands.
        # Snapshot path — no live channel, so read the durable state and poll.
        yield ResearchStart(run_id=run_id, trip_id=run.trip_id or "").to_sse()
        yield ResearchPhase(
            todos=[{"content": "research", "status": run.status}]
        ).to_sse()
        while True:
            current = service.status(run_id)
            status = current.status if current is not None else "failed"
            if status in _TERMINAL:
                if status == "completed":
                    yield ResearchDone(
                        status=status,
                        files=_file_index(store, run.user_id, run.trip_id),
                        proposal_ready=_proposal_ready(store, run.user_id, run.trip_id),
                    ).to_sse()
                else:
                    yield ResearchError(
                        code=status, message="research run did not complete"
                    ).to_sse()
                return
            await asyncio.sleep(2)

    return sse_response(_events())
