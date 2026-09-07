"""Background-extraction metrics: run_memory_extraction → agent_runs.background_* (SC-7)."""

import json

import app.memory.extraction_runner as runner
import pytest
from app.clients.llm import FakeLLM
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import AgentRun
from app.memory.extraction_runner import run_memory_extraction
from app.repositories.agent_run import AgentRunRepository
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.store.memory import InMemoryStore

MESSAGES = [
    HumanMessage(content="I love window seats and I'm vegetarian."),
    AIMessage(content="Noted — window seat, vegetarian meals."),
]

EXTRACTOR_JSON = json.dumps(
    {
        "preferences": [{"key": "seat", "text": "prefers window seats"}],
        "instructions": [],
        "episodes": [],
    }
)


@pytest.fixture
def factory(tmp_db):
    f = get_session_factory(tmp_db)
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    with f() as s:
        s.query(AgentRun).delete()
        s.commit()
    return f


def _seed_run(factory, run_id="run-bg"):
    AgentRunRepository(factory).start(
        run_id,
        user_id="u1",
        conversation_id="c1",
        thread_id="t1",
        trip_id=None,
        channel="chat",
        kind="turn",
        started_at="2026-09-03T00:00:00+00:00",
    )


def test_records_background_metrics_without_touching_turn_columns(factory):
    _seed_run(factory)
    llm = FakeLLM(responses=[EXTRACTOR_JSON])

    run_memory_extraction(
        messages=MESSAGES,
        user_id="u1",
        trip_id=None,
        plan_approved=False,
        allow_memory_write=True,
        store=InMemoryStore(),
        llm=llm,
        run_id="run-bg",
        session_factory=factory,
    )

    row = AgentRunRepository(factory).list_recent()[0]
    # FakeLLM emits one call with usage input=10/output=5 → 15 background tokens.
    assert row.background_llm_calls == 1
    assert row.background_tokens == 15
    assert row.background_ms >= 0
    # Turn columns are untouched by background extraction.
    assert row.llm_calls == 0
    assert row.input_tokens == 0


def test_no_run_id_makes_no_db_access(factory, monkeypatch):
    called = False

    def _boom(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("AgentRunRepository must not be constructed")

    monkeypatch.setattr(runner, "AgentRunRepository", _boom)
    llm = FakeLLM(responses=[EXTRACTOR_JSON])

    run_memory_extraction(
        messages=MESSAGES,
        user_id="u1",
        trip_id=None,
        plan_approved=False,
        allow_memory_write=True,
        store=InMemoryStore(),
        llm=llm,
    )

    assert called is False
