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
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from deepagents.backends.store import StoreBackend
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import _utc_now_iso
from app.db.locks import advisory_xact_lock
from app.db.models.agent_run import AgentRun
from app.exceptions import ConflictError, NotFoundError, RateLimitError
from app.repositories.agent_run import AgentRunRepository
from app.repositories.rate_limit import RateLimitRepository
from app.repositories.trip import TripRepository
from app.research.context import ResearchContext
from app.research.progress import ProgressBus

logger = logging.getLogger(__name__)

RESEARCH_KIND = "research"
RESEARCH_CHANNEL = "research"
_RUNNING = "running"
_INTERRUPTED = "interrupted"
_DEFAULT_LANGUAGE = "en"
RESEARCH_START_BUCKET = "research_start"
_DAY_SECONDS = 24 * 60 * 60

# Dossier / plan store routes collapse onto one namespace; a user-facing path keeps
# its route prefix, the store key drops it (mirrors the composite backend strip).
_ROUTE_PREFIXES = ("/research", "/plan", "/memory")


def research_thread_id(
    user_id: str,
    trip_id: str,
) -> str:
    """The per-dossier checkpoint thread id (design §4): one thread per trip."""
    return f"research:{user_id}:{trip_id}"


def research_lock_name(
    user_id: str,
    trip_id: str,
) -> str:
    """The advisory-lock subject that serializes ``start`` for one trip's dossier.
    Keyed per (user, trip) — the granularity of the one-run-per-trip rule — so a
    user's other trips are never blocked."""
    return f"research_start:{user_id}:{trip_id}"


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
        bus: ProgressBus | None,
    ) -> None:
        self._sf = session_factory
        self._store = store
        self._agent = agent
        self._bus = bus

    # -- launch / resume -------------------------------------------------

    @property
    def runnable(self) -> bool:
        """Whether a booked run can actually be driven — ``False`` when no research
        agent was built (flag off or build failed). The chat node checks this before
        ``start`` so it never books a row nothing can execute."""
        return self._agent is not None

    def start(
        self,
        user_id: str,
        trip_id: str,
        instruction: str | None = None,
    ) -> str:
        """Book a fresh research run and return its id. The caller schedules the
        runner — the REST surface via ``BackgroundTasks`` (``routers/research.py``),
        the chat node via :meth:`launch`. Raises ``NotFoundError`` if the trip is not
        the caller's, ``ConflictError`` if a run for this trip is already ``running``,
        ``RateLimitError`` over the per-user daily cap."""
        if TripRepository(self._sf).get_trip(trip_id, user_id) is None:
            raise NotFoundError("Trip not found")
        run_id = str(uuid4())
        # One transaction holds a per-trip advisory lock across the check AND the
        # insert, so two concurrent starts for the same trip serialize: the first
        # books the run, the second wakes to see the running row and raises. Without
        # this both could pass the guard and drive the same checkpoint thread + store
        # namespace, corrupting each other's dossier. No-op on SQLite (sequential).
        with self._sf() as s:
            advisory_xact_lock(s, research_lock_name(user_id, trip_id))
            if self._running_for(s, trip_id) is not None:
                raise ConflictError(
                    "A research run is already in progress for this trip"
                )
            # Spent only once the lock says this start wins, so a 409 — including
            # the loser of a double click — never costs a slot.
            self._spend_daily_cap(user_id)
            self._insert_run(run_id, user_id, trip_id, session=s)
            s.commit()
        self._open_on_bus(run_id)
        return run_id

    async def launch(
        self,
        run_id: str,
        user_id: str,
        trip_id: str,
        instruction: str | None = None,
    ) -> None:
        """Drive a freshly booked run (from :meth:`start`) to a terminal state.

        A graph node cannot use FastAPI ``BackgroundTasks``, so the chat launcher
        schedules this coroutine with ``asyncio.create_task``; the REST surface
        schedules the runner directly. Never raises — the runner folds every
        failure (timeout included) into the run row (``runner.run_trip_research``)."""
        ctx = self._context(run_id, user_id, trip_id)
        await self._drive(run_id, ctx, instruction=instruction, resumed_from=None)

    async def resume(self, run_id: str) -> str:
        """Resume an interrupted run's checkpointed thread under a new run row whose
        first step records ``resumed_from`` (design §4), and drive it to a terminal
        state. Raises ``NotFoundError`` if the prior run is unknown."""
        prior = self._get_run(run_id)
        if prior is None:
            raise NotFoundError("Research run not found")
        new_run_id = str(uuid4())
        self._insert_run(new_run_id, prior.user_id, prior.trip_id)
        self._open_on_bus(new_run_id)
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
        *,
        session: Session | None = None,
    ) -> None:
        # A caller-owned ``session`` keeps the insert inside the lock's transaction
        # (the repo flushes; the caller commits); ``start`` uses this. ``resume``
        # passes none and the repo commits on its own factory session.
        AgentRunRepository(session if session is not None else self._sf).start(
            run_id,
            user_id=user_id,
            conversation_id=research_thread_id(user_id, trip_id),
            thread_id=research_thread_id(user_id, trip_id),
            trip_id=trip_id,
            channel=RESEARCH_CHANNEL,
            kind=RESEARCH_KIND,
            started_at=_utc_now_iso(),
        )

    def _open_on_bus(self, run_id: str) -> None:
        """Make the booked run live on the bus now: the client opens the stream on
        the 202, before the runner's first event, and the SSE route only tails a
        run the bus already reports live. The runner closes it on every exit."""
        if self._bus is not None:
            self._bus.open(run_id)

    def _spend_daily_cap(self, user_id: str) -> None:
        """Count one booking against ``research_start`` (design §5). It lives here, not
        on a route, because every launch path books through ``start``: the REST start,
        the REST revise and the chat node. Committed on its own session, so the hit
        counts even if the booking then fails."""
        limit = get_settings().research_daily_limit
        decision = RateLimitRepository(self._sf).hit(
            bucket=RESEARCH_START_BUCKET,
            subject=user_id,
            now_epoch=int(time.time()),
            limit=limit,
            window_seconds=_DAY_SECONDS,
        )
        if not decision.allowed:
            raise RateLimitError(
                "Daily research limit reached.",
                retry_after=decision.retry_after,
                limit=limit,
                remaining=decision.remaining,
                reset_at=decision.reset_at,
                hint="Wait for the Retry-After window, then retry.",
            )

    def _running_for(self, session: Session, trip_id: str) -> AgentRun | None:
        """The trip's ``running`` research run, if any, read on the caller's
        locked ``session`` so the check shares the insert's transaction."""
        return session.scalars(
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
