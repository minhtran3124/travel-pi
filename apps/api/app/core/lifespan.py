"""Application lifespan — startup and shutdown hooks (schema, seed, and caches set up here, not at import time)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.agent_config_cache import AgentConfigCache, reload_from_db
from app.core.config import get_settings
from app.core.invariants import check_city_coverage
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.research.progress import ProgressBus
from app.research.runtime import set_research_runtime
from app.services import booking_service, saved_place_service, trip_service
from app.services.flight_service import init_flight_index

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup tasks, yield while the app serves, then shut down."""
    settings = get_settings()
    logger.info("Database URL: %s", settings.database_url)
    engine = get_engine(settings.database_url)
    # SQLite self-creates its schema; Postgres schema is managed by Alembic.
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine, checkfirst=True)

    # Seed read-only reference entities before any check reads them; idempotent, so re-runs are safe.
    seed_all(get_session_factory(settings.database_url))

    # Populate the per-agent LLM config cache so overrides resolve from the first
    # request; ``configure`` wires the loader + poll interval for lazy refresh.
    _config_factory = get_session_factory(settings.database_url)
    AgentConfigCache.configure(
        _config_factory, settings.agent_config_poll_interval_seconds
    )
    reload_from_db(_config_factory)

    # Enforce the "every city has ≥3 hotels and ≥3 places" contract from CLAUDE.md.
    check_city_coverage()

    # Pre-warm the travel-knowledge RAG store so the concierge tool works from the
    # first request; wrapped so a failure never blocks startup (RAG degrades to no results).
    try:
        from langchain_core.vectorstores import InMemoryVectorStore

        from app.rag.embeddings import get_vector_store
        from app.rag.ingest import ingest_knowledge

        store = get_vector_store()
        # A persisted backend keeps the corpus across restarts — skip re-embed when
        # already populated; the in-memory store is ephemeral so it always needs ingesting.
        already_ingested = False
        if not isinstance(store, InMemoryVectorStore):
            try:
                already_ingested = bool(store.similarity_search("visa", k=1))
            except Exception:
                already_ingested = False
        if already_ingested:
            logger.info(
                "Travel knowledge RAG already ingested in %s; skipping re-embed",
                type(store).__name__,
            )
        else:
            with get_session_factory(settings.database_url)() as session:
                count = ingest_knowledge(store, session)
            logger.info(
                "Travel knowledge RAG ready: %d documents in %s",
                count,
                type(store).__name__,
            )
    except Exception:
        logger.exception("Travel knowledge RAG pre-warm failed; tool degrades to empty")

    # Idempotent per-service init keeps each service constructable in tests; no-ops on Postgres after Alembic.
    try:
        booking_service.init_db()
        trip_service.init_db()
        saved_place_service.init_db()
        init_flight_index()
    except Exception:
        logger.exception("Could not initialise database at %s", settings.database_url)
        raise

    # Build the agent graph once and share via app.state (rebuilding per request
    # leaked a connection); backends degrade to in-memory so a missing Postgres never blocks startup.
    from app.agents.checkpointer import open_checkpointer
    from app.agents.graph import build_graph
    from app.memory.store import open_store

    async with (
        open_checkpointer(settings.database_url) as checkpointer,
        open_store(settings.database_url) as store,
    ):
        try:
            # Stash the backends + config generation so the graph can be rebuilt
            # in-place when the DB config changes, reusing the same checkpointer/store.
            app.state.agent_checkpointer = checkpointer
            app.state.agent_store = store
            app.state.travel_graph = build_graph(checkpointer=checkpointer, store=store)
            app.state.travel_graph_gen = AgentConfigCache.generation()
            logger.info(
                "Agent graph ready: checkpointer=%s store=%s",
                type(checkpointer).__name__,
                type(store).__name__,
            )
        except Exception:
            logger.exception("Agent graph build failed; agent endpoints disabled")
            app.state.travel_graph = None

        # The trip-research deep agent is a second, independent graph sharing this
        # checkpointer/store; it is off until wave 4 flips ``research_enabled``. Its
        # build is isolated in its own try/except so a failure never touches the chat
        # graph above — research routes degrade to 503 with the agent left None.
        app.state.research_agent = None
        app.state.research_bus = ProgressBus()
        if settings.research_enabled:
            try:
                from app.research.agent import build_research_agent
                from app.research.service import ResearchService

                app.state.research_agent = build_research_agent(
                    store=store, checkpointer=checkpointer
                )
                ResearchService(
                    session_factory=get_session_factory(settings.database_url),
                    store=store,
                    agent=app.state.research_agent,
                    bus=app.state.research_bus,
                ).sweep_stale()
                # Share the built agent + bus with the chat graph's ``research``
                # node (which was wired before this agent existed) and the REST
                # routes, so both drive one agent through one bus. On the failure
                # path below the holder is left unset, so the node declines.
                set_research_runtime(app.state.research_agent, app.state.research_bus)
                logger.info("Trip-research agent ready")
            except Exception:
                logger.exception("Trip-research agent build failed; research disabled")
                app.state.research_agent = None

        logger.info("Startup complete — bookings, trips, and flight-index tables ready")
        yield
    logger.info("Shutting down")
