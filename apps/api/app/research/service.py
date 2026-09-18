"""Trip-research run orchestration: ownership, run bookkeeping, resume, files, sweep.

The router stays thin — validation, then this service, then HTTP mapping (design §5).
``ResearchService`` owns the ownership check (trip must belong to the caller), the
one-run-per-trip rule, the ``agent_runs`` bookkeeping (``kind``/``channel`` =
``"research"``, thread id ``research:{uid}:{trip}``), thread resume, dossier file
access, and the stale-run sweep. All DB work goes through the shared session factory;
background code never reuses a request session.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from deepagents.backends.store import StoreBackend
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import _utc_now_iso
from app.db.models.agent_run import AgentRun
from app.exceptions import ConflictError, NotFoundError
from app.repositories.agent_run import AgentRunRepository
from app.repositories.trip import TripRepository
from app.research.context import ResearchContext
from app.research.progress import ProgressBus

logger = logging.getLogger(__name__)

RESEARCH_KIND = "research"
RESEARCH_CHANNEL = "research"
_RUNNING = "running"
_INTERRUPTED = "interrupted"
_DEFAULT_LANGUAGE = "en"

# Dossier / plan store routes collapse onto one namespace; a user-facing path keeps
# its route prefix, the store key drops it (mirrors the composite backend strip).
_ROUTE_PREFIXES = ("/research", "/plan", "/memory")


def research_thread_id(
    user_id: str,
    trip_id: str,
) -> str:
    """The per-dossier checkpoint thread id (design §4): one thread per trip."""
    return f"research:{user_id}:{trip_id}"


def _store_key(path: str) -> str:
    """Map a user-facing dossier path (``/research/flights.md``) to its store key
    (``/flights.md``), stripping the route prefix as the composite backend does."""
    p = path if path.startswith("/") else f"/{path}"
    for prefix in _ROUTE_PREFIXES:
        if p == prefix:
            return "/"
        if p.startswith(f"{prefix}/"):
            return p[len(prefix) :]
    return p


class ResearchService:
    """Ownership, run bookkeeping, resume and dossier access for the research agent."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        store: BaseStore,
        agent: CompiledStateGraph | None,
        bus: ProgressBus,
    ) -> None:
        self._sf = session_factory
        self._store = store
        self._agent = agent
        self._bus = bus

    # -- launch / resume -------------------------------------------------

    def start(
        self,
        user_id: str,
        trip_id: str,
        instruction: str | None = None,
    ) -> str:
        """Book a fresh research run and return its id (the router schedules the
        runner). Raises ``NotFoundError`` if the trip is not the caller's,
        ``ConflictError`` if a run for this trip is already ``running``."""
        if TripRepository(self._sf).get_trip(trip_id, user_id) is None:
            raise NotFoundError("Trip not found")
        if self._running_for(trip_id) is not None:
            raise ConflictError("A research run is already in progress for this trip")
        run_id = str(uuid4())
        self._insert_run(run_id, user_id, trip_id)
        return run_id

    async def resume(self, run_id: str) -> str:
        """Resume an interrupted run's checkpointed thread under a new run row whose
        first step records ``resumed_from`` (design §4), and drive it to a terminal
        state. Raises ``NotFoundError`` if the prior run is unknown."""
        prior = self._get_run(run_id)
        if prior is None:
            raise NotFoundError("Research run not found")
        new_run_id = str(uuid4())
        self._insert_run(new_run_id, prior.user_id, prior.trip_id)
        ctx = self._context(new_run_id, prior.user_id, prior.trip_id)
        await self._drive(new_run_id, ctx, instruction=None, resumed_from=run_id)
        return new_run_id

    async def _drive(
        self,
        run_id: str,
        ctx: ResearchContext,
        *,
        instruction: str | None,
        resumed_from: str | None,
    ) -> None:
        # Lazy import breaks the runner <-> service cycle (runner imports thread id).
        from app.research.runner import run_trip_research

        await run_trip_research(
            run_id=run_id,
            ctx=ctx,
            instruction=instruction,
            agent=self._agent,
            bus=self._bus,
            session_factory=self._sf,
            resumed_from=resumed_from,
        )

    # -- queries ---------------------------------------------------------

    def status(self, run_id: str) -> AgentRun | None:
        """The run row, or ``None`` if unknown."""
        return self._get_run(run_id)

    def latest(self, trip_id: str) -> AgentRun | None:
        """The most recent research run for the trip, or ``None``."""
        with self._sf() as s:
            return s.scalars(
                select(AgentRun)
                .where(AgentRun.trip_id == trip_id, AgentRun.kind == RESEARCH_KIND)
                .order_by(AgentRun.created_at.desc())
            ).first()

    # -- dossier files ---------------------------------------------------

    def file(self, run_id: str, path: str) -> str | None:
        """Dossier file content (utf-8), or ``None`` if absent. Raises
        ``NotFoundError`` if the run is unknown."""
        run = self._require_run(run_id)
        backend = self._file_backend(run.user_id, run.trip_id)
        resp = backend.download_files([_store_key(path)])[0]
        if resp.error is not None or resp.content is None:
            return None
        return resp.content.decode("utf-8")

    def write_file(self, run_id: str, path: str, content: str) -> None:
        """Persist a user edit into the dossier namespace (design §5). Raises
        ``NotFoundError`` if the run is unknown."""
        run = self._require_run(run_id)
        backend = self._file_backend(run.user_id, run.trip_id)
        backend.upload_files([(_store_key(path), content.encode("utf-8"))])

    # -- sweep -----------------------------------------------------------

    def sweep_stale(self) -> int:
        """Flip research rows still ``running`` past ``research_stale_minutes`` to
        ``interrupted`` (design §4). Returns the number of rows swept."""
        minutes = get_settings().research_stale_minutes
        cutoff = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
        with self._sf() as s:
            result = s.execute(
                update(AgentRun)
                .where(
                    AgentRun.kind == RESEARCH_KIND,
                    AgentRun.status == _RUNNING,
                    AgentRun.started_at < cutoff,
                )
                .values(status=_INTERRUPTED)
            )
            s.commit()
            return int(result.rowcount or 0)

    # -- internals -------------------------------------------------------

    def _context(
        self,
        run_id: str,
        user_id: str,
        trip_id: str,
    ) -> ResearchContext:
        return ResearchContext(
            user_id=user_id,
            trip_id=trip_id,
            run_id=run_id,
            language=_DEFAULT_LANGUAGE,
            timezone=get_settings().agent_timezone,
        )

    def _insert_run(
        self,
        run_id: str,
        user_id: str,
        trip_id: str,
    ) -> None:
        AgentRunRepository(self._sf).start(
            run_id,
            user_id=user_id,
            conversation_id=research_thread_id(user_id, trip_id),
            thread_id=research_thread_id(user_id, trip_id),
            trip_id=trip_id,
            channel=RESEARCH_CHANNEL,
            kind=RESEARCH_KIND,
            started_at=_utc_now_iso(),
        )

    def _running_for(self, trip_id: str) -> AgentRun | None:
        with self._sf() as s:
            return s.scalars(
                select(AgentRun).where(
                    AgentRun.trip_id == trip_id,
                    AgentRun.kind == RESEARCH_KIND,
                    AgentRun.status == _RUNNING,
                )
            ).first()

    def _get_run(self, run_id: str) -> AgentRun | None:
        with self._sf() as s:
            return s.get(AgentRun, run_id)

    def _require_run(self, run_id: str) -> AgentRun:
        run = self._get_run(run_id)
        if run is None:
            raise NotFoundError("Research run not found")
        return run

    def _file_backend(self, user_id: str, trip_id: str) -> StoreBackend:
        namespace = ("users", user_id, RESEARCH_KIND, trip_id)
        return StoreBackend(store=self._store, namespace=lambda _rt: namespace)
