"""Helpers shared by the research-router API tests (Task 4.1).

Offline only: a temp-SQLite DB (via a ``get_session`` override), a fake research
agent stashed on ``app.state`` (mirroring how the chat tests stash the graph), an
``InMemoryStore`` for the dossier, and an in-process ``ProgressBus``. The TestClient
is used WITHOUT its context manager so the real lifespan never runs (it would
rebuild the store/agent and clobber ``app.state``); background tasks still run after
each response.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.auth import AuthUser, get_current_user
from app.db.base import Base, _utc_now_iso
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.repositories.agent_run import AgentRunRepository
from app.repositories.user import UserRepository
from app.research.progress import ProgressBus
from app.research.service import RESEARCH_CHANNEL, RESEARCH_KIND, research_thread_id
from langgraph.store.memory import InMemoryStore

USER_ID = "u1"


class FakeResearchAgent:
    """The minimum the runner + router need: a ``store`` and an empty event stream."""

    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    async def astream_events(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict]:
        async def _gen() -> AsyncIterator[dict]:
            return
            yield  # pragma: no cover — marks this an async generator

        return _gen()


def _seed_premium(url: str, user_id: str) -> None:
    s = get_session_factory(url)()
    try:
        UserRepository(s).upsert_tier(user_id, "premium")
        s.commit()
    finally:
        s.close()


def build_app(
    tmp_path,
    *,
    premium: bool = True,
    user_id: str = USER_ID,
):
    """Build an app bound to a fresh temp DB with fake research state on app.state.

    The caller must have set ``RESEARCH_ENABLED`` (and cleared the settings cache)
    before calling, so ``create_app`` decides router registration on the flag.
    """
    url = f"sqlite:///{tmp_path / 'research_api.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    if premium:
        _seed_premium(url, user_id)

    app = create_app()

    def _override_session():
        s = get_session_factory(url)()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id=user_id, email=None, role=None, claims={}
    )
    store = InMemoryStore()
    app.state.research_agent = FakeResearchAgent(store)
    app.state.research_bus = ProgressBus()
    return app, url, store


def create_trip(url: str, trip_id: str, user_id: str) -> None:
    from app.db import models

    s = get_session_factory(url)()
    try:
        s.add(
            models.Trip(
                id=trip_id,
                user_id=user_id,
                title="Trip",
                city="Da Nang",
                travelers=1,
                created_at=_utc_now_iso(),
            )
        )
        s.commit()
    finally:
        s.close()


def insert_run(
    url: str,
    run_id: str,
    user_id: str,
    trip_id: str,
    *,
    status: str = "running",
) -> None:
    repo = AgentRunRepository(get_session_factory(url))
    repo.start(
        run_id,
        user_id=user_id,
        conversation_id=research_thread_id(user_id, trip_id),
        thread_id=research_thread_id(user_id, trip_id),
        trip_id=trip_id,
        channel=RESEARCH_CHANNEL,
        kind=RESEARCH_KIND,
        started_at=_utc_now_iso(),
    )
    if status != "running":
        repo.finish(
            run_id,
            status=status,
            current_flow=RESEARCH_KIND,
            finished_at=_utc_now_iso(),
            metrics={},
        )
