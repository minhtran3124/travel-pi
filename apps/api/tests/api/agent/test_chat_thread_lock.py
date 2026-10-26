"""gh-289: two simultaneous /agent/chat turns on one thread must not interleave.

Postgres-only (advisory locks); skips on the default SQLite run. ``agent_chat``
commits mid-turn, so a transaction-scoped lock would not hold: the guard is
session-level on a dedicated connection.
"""

import asyncio
import os
import uuid

import httpx
import pytest
from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.main import create_app
from app.routers.agent import get_travel_graph, get_travel_graph_optional
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from sqlalchemy import text

PG_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not PG_URL.startswith("postgresql"), reason="advisory locks need Postgres"
)


class _GatedGraph:
    """Delegates to a real graph, but ``ainvoke`` waits on a gate so a turn stays in flight."""

    def __init__(self, inner, gate: asyncio.Event, fail: bool = False):
        self._inner, self._gate, self._fail = inner, gate, fail
        self.entered = asyncio.Event()

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def ainvoke(self, *a, **kw):
        self.entered.set()
        await self._gate.wait()
        if self._fail:
            raise RuntimeError("boom")
        return await self._inner.ainvoke(*a, **kw)


def _app(graph):
    Base.metadata.create_all(get_engine(PG_URL), checkfirst=True)
    app = create_app()

    def _session():
        s = get_session_factory(PG_URL)()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: AuthUser(
        id="u289", email=None, role=None, claims={}
    )
    app.dependency_overrides[get_travel_graph] = lambda: graph
    app.dependency_overrides[get_travel_graph_optional] = lambda: graph
    return app


def _real_graph():
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="concierge")] * 6,
        responses=["ok"] * 6,
    )
    return build_graph(
        llm=main,
        fast_llm=FakeLLM(responses=["OK"] * 6),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )


def _body() -> dict:
    return {"message": "hi", "conversation_id": str(uuid.uuid4())}


def _double_post(body: dict, fail: bool):
    gate = asyncio.Event()
    gated = _GatedGraph(_real_graph(), gate, fail=fail)
    app = _app(gated)

    async def run():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            first = asyncio.create_task(c.post("/agent/chat", json=body))
            await asyncio.wait_for(gated.entered.wait(), 10)
            try:
                # Unguarded, the second turn also blocks on the gate; time out so that fails fast.
                second = await asyncio.wait_for(c.post("/agent/chat", json=body), 5)
            except asyncio.TimeoutError:
                second = None
            finally:
                gate.set()
            return await first, second

    return asyncio.run(run())


def _held_locks() -> int:
    with get_engine(PG_URL).connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")
        ).scalar_one()


def test_concurrent_double_post_one_200_one_409():
    first, second = _double_post(_body(), fail=False)
    assert first.status_code == 200
    assert second is not None, "second turn ran concurrently instead of being rejected"
    assert second.status_code == 409
    assert _held_locks() == 0


def test_lock_released_after_failed_turn():
    body = _body()
    _, second = _double_post(body, fail=True)
    assert second is not None and second.status_code == 409
    assert _held_locks() == 0

    # Same thread is usable again: nothing is left holding it.
    gate = asyncio.Event()
    gate.set()
    app = _app(_GatedGraph(_real_graph(), gate))

    async def again():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.post("/agent/chat", json=body)

    assert asyncio.run(again()).status_code == 200
