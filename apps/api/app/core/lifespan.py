"""Application lifespan — startup and shutdown hooks.

Importing a module should have no side effects, so the SQLite tables are
created here (on startup) rather than at import time.
"""

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
from app.services import booking_service, saved_place_service, trip_service
from app.services.flight_service import init_flight_index

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run startup tasks, yield while the app serves, then shut down.

    :param app: The FastAPI app whose startup/shutdown this manages.
    """
    settings = get_settings()
    logger.info("Database URL: %s", settings.database_url)
    engine = get_engine(settings.database_url)
    # SQLite (local/dev/test) self-creates its schema; Postgres schema is
    # managed by Alembic (alembic upgrade head, run by the container entrypoint).
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine, checkfirst=True)

    # Seed the read-only reference entities from app/data BEFORE any check that
    # reads them. Idempotent (merge + City natural-key upsert), so re-runs are
    # safe. On Postgres the schema is already created by Alembic; seeding here
    # populates a fresh DB so the later (Chunk E) DB-backed coverage check has
    # data to read.
    seed_all(get_session_factory(settings.database_url))

    # Populate the per-agent LLM config cache from the DB, so get_agent_llm
    # resolves DB overrides from the first request. Safe on an empty table
    # (reload_from_db just syncs an empty map). ``configure`` wires the TTL +
    # loader so later reads refresh lazily (MIN-47) without a restart.
    _config_factory = get_session_factory(settings.database_url)
    AgentConfigCache.configure(
        _config_factory, settings.agent_config_poll_interval_seconds
    )
    reload_from_db(_config_factory)

    # Enforce the "every city has ≥3 hotels and ≥3 places" promise from
    # CLAUDE.md — a typo in seed data would otherwise only surface when a
    # user searched the affected city.
    check_city_coverage()

    # Pre-warm the travel-knowledge RAG store (specs/travel-knowledge-rag) so the
    # concierge's `search_travel_knowledge` tool works from the first request. The
    # store is a cached singleton keyed by DATABASE_URL; ingest_knowledge embeds the
    # visa + tips + summaries corpus with stable ids (idempotent upsert). Wrapped so
    # a failure never blocks startup — RAG degrades to "no results", the concierge
    # answers from its other tools. Postgres reads the persisted collection; this
    # keeps it current after a seed change.
    try:
        from langchain_core.vectorstores import InMemoryVectorStore

        from app.rag.embeddings import get_vector_store
        from app.rag.ingest import ingest_knowledge

        store = get_vector_store()
        # A persisted backend (pgvector) keeps the corpus across restarts, so skip
        # the re-embed when the collection is already populated — otherwise every
        # boot (and every worker) re-calls the embeddings API for the whole corpus.
        # The in-memory store (tests/SQLite) is ephemeral per process, so it always
        # needs ingesting. After a seed change on Postgres, re-run
        # ``scripts/ingest_rag.py`` to refresh the persisted collection.
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

    # The per-service init_db() calls (also create_all, idempotent) keep each
    # service constructable/initable independently in tests; on Postgres they
    # are no-ops after Alembic has run (checkfirst=True).
    try:
        booking_service.init_db()
        trip_service.init_db()
        saved_place_service.init_db()
        init_flight_index()
    except Exception:
        logger.exception("Could not initialise database at %s", settings.database_url)
        raise

    # Agent graph — built ONCE here and shared via app.state (REVIEW.md C1: the
    # router used to rebuild the graph + checkpointer + store on every request,
    # leaking a connection each call). The checkpointer/store context managers are
    # held open for the process lifetime and closed on shutdown. Both degrade to
    # in-memory if their backend can't initialise, so a missing Postgres never
    # blocks startup. Lazy imports keep module import side-effect-free.
    from app.agents.checkpointer import open_checkpointer
    from app.agents.graph import build_graph
    from app.memory.store import open_store

    async with (
        open_checkpointer(settings.database_url) as checkpointer,
        open_store(settings.database_url) as store,
    ):
        try:
            # Stash the backends + config generation so the graph can be rebuilt
            # in-place when the DB config changes (MIN-47), reusing the same
            # process-lifetime checkpointer/store (no connection leak).
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

        logger.info("Startup complete — bookings, trips, and flight-index tables ready")
        yield
    logger.info("Shutting down")
