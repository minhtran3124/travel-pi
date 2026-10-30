"""Cheap app/DB setup for tests that build their own per-user TestClient.

Entering ``with TestClient(create_app())`` runs the real lifespan: re-seed,
RAG ingest, agent graph, research agent (~1 s each). Ownership/permission tests
seed their own DB and never touch ``app.state``, so they skip it.
"""

from contextlib import asynccontextmanager

from app.db.engine import get_session_factory
from app.db.seed import seed_all
from app.main import create_app

_seeded: set[str] = set()


def ensure_seeded(url: str) -> None:
    """``seed_all`` once per DB url per process (it is a ~0.7 s idempotent upsert)."""
    if url not in _seeded:
        seed_all(get_session_factory(url))
        _seeded.add(url)


@asynccontextmanager
async def _no_lifespan(app):
    yield


def create_app_without_lifespan():
    """``create_app()`` whose startup/shutdown does nothing."""
    app = create_app()
    app.router.lifespan_context = _no_lifespan
    return app
