"""The main agent can read the trip it is researching.

The prompt's first step is ``get_trip_summary``, and the Research tab starts a run with
only a generic instruction — so the summary is the agent's ONLY source for destination,
dates and party. With the tool unbound, the call fails and every dimension is researched
blind (PR #221 review).
"""

from __future__ import annotations

import pytest
from app.clients.llm import FakeLLM
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.research.context import ResearchContext
from app.schemas.trip import TripCreate
from app.services.trip_service import TripService
from langchain_core.messages import ToolMessage

from tests.research.conftest import USER_ID, RecordingFakeLLM, build


@pytest.fixture
def trip_id(tmp_path, monkeypatch) -> str:
    url = f"sqlite:///{tmp_path / 'research.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    with get_session_factory(url)() as s:
        trip = TripService(s, USER_ID).create_trip(
            TripCreate(title="Tokyo trip", city="Tokyo")
        )
        s.commit()
        trip_id = trip.id
    yield trip_id
    get_settings.cache_clear()


def test_main_agent_binds_get_trip_summary(store) -> None:
    agent = build(store, llm=RecordingFakeLLM(responses=[{"content": "done"}]))
    agent.invoke(
        {"messages": [{"role": "user", "content": "research my trip"}]},
        {"configurable": {"thread_id": "research:u1:t1"}},
        context=ResearchContext(
            user_id=USER_ID, trip_id="t1", run_id="r1", language="en", timezone="UTC"
        ),
    )
    assert "get_trip_summary" in RecordingFakeLLM._bound


def test_main_agent_reads_the_run_trip(store, trip_id) -> None:
    model = FakeLLM(
        responses=[
            {
                "content": "",
                "tool_calls": [{"name": "get_trip_summary", "args": {}, "id": "c1"}],
            },
            {"content": "done"},
        ]
    )
    agent = build(store, llm=model)
    result = agent.invoke(
        {
            "messages": [{"role": "user", "content": "Research this trip in depth."}],
            "trip_id": trip_id,
            "user_id": USER_ID,
        },
        {"configurable": {"thread_id": f"research:{USER_ID}:{trip_id}"}},
        context=ResearchContext(
            user_id=USER_ID,
            trip_id=trip_id,
            run_id="r1",
            language="en",
            timezone="UTC",
        ),
    )

    replies = [
        m
        for m in result["messages"]
        if isinstance(m, ToolMessage) and m.name == "get_trip_summary"
    ]
    assert len(replies) == 1
    assert replies[0].status != "error", replies[0].content
    assert "Tokyo" in replies[0].content
