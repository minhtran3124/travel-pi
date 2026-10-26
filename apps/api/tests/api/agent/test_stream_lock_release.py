"""The SSE same-thread lock must be released even when the response body is never iterated
(client gone before Starlette starts streaming) and must survive cancellation."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import anyio
import pytest
from app.routers import agent as agent_router
from app.schemas.agent import ChatRequest
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse


@pytest.mark.anyio
async def test_stream_lock_released_when_body_never_iterated(monkeypatch):
    state = {"held": False, "prior_ran": False}

    @asynccontextmanager
    async def fake_lock(*_a, **_kw):
        state["held"] = True
        try:
            yield
        finally:
            state["held"] = False

    async def prior():
        # Memory extraction runs after the lock is gone.
        state["prior_ran"] = not state["held"]

    async def fake_agent_stream(*_a, **_kw):
        async def body():
            yield b"data: x\n\n"

        return StreamingResponse(body(), background=BackgroundTask(prior))

    monkeypatch.setattr(agent_router, "advisory_session_lock", fake_lock)
    monkeypatch.setattr(agent_router, "_agent_stream", fake_agent_stream)

    response = await agent_router.agent_stream(
        ChatRequest(message="hi", conversation_id=str(uuid.uuid4())),
        MagicMock(),
        MagicMock(),
        MagicMock(id="u1"),
    )
    assert state["held"] is True
    # Body is never iterated; Starlette still runs response.background after the call.
    await response.background()
    assert state["held"] is False
    assert state["prior_ran"] is True


@pytest.mark.anyio
async def test_session_lock_release_is_shielded_from_cancellation(monkeypatch):
    from app.db import locks

    eng = MagicMock()
    conn = eng.connect.return_value.execution_options.return_value
    conn.execute.return_value.scalar.return_value = True
    monkeypatch.setattr(locks, "_lock_engine", lambda url: eng)
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    session.get_bind.return_value.engine.url.render_as_string.return_value = "x"

    with anyio.CancelScope() as scope:
        async with locks.advisory_session_lock(session, "t", "busy"):
            scope.cancel()
    conn.close.assert_called_once()
