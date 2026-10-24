"""Background extraction spend lands in agent_runs.cost_usd / by_model (#270)."""

import json

import pytest
from app.clients.llm import FakeLLM
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import AgentRun
from app.memory.extraction_runner import run_memory_extraction
from app.repositories.agent_run import AgentRunRepository
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.store.memory import InMemoryStore

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


def test_extraction_usage_is_merged_into_by_model(factory):
    _seed_run(factory)
    run_memory_extraction(
        messages=[HumanMessage(content="window seats"), AIMessage(content="noted")],
        user_id="u1",
        trip_id=None,
        plan_approved=False,
        allow_memory_write=True,
        store=InMemoryStore(),
        llm=FakeLLM(responses=[EXTRACTOR_JSON]),
        run_id="run-bg",
        session_factory=factory,
    )
    row = AgentRunRepository(factory).list_recent()[0]
    assert row.by_model, "background model usage must be merged into by_model"
    usage = next(iter(row.by_model.values()))
    assert usage["input_tokens"] == 10 and usage["output_tokens"] == 5


def test_add_background_merges_by_model_and_cost(factory):
    _seed_run(factory)
    repo = AgentRunRepository(factory)
    with factory() as s:
        r = s.get(AgentRun, "run-bg")
        r.cost_usd = 0.5
        r.by_model = {
            "claude-sonnet-5-5": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cached_tokens": 0,
                "calls": 2,
            }
        }
        s.commit()
    repo.add_background(
        "run-bg",
        llm_calls=1,
        tokens=30,
        ms=5,
        cost_usd=0.25,
        by_model={
            "claude-sonnet-5-5": {
                "input_tokens": 20,
                "output_tokens": 10,
                "cached_tokens": 0,
                "calls": 1,
            },
            "claude-haiku-5-5": {
                "input_tokens": 1,
                "output_tokens": 1,
                "cached_tokens": 0,
                "calls": 1,
            },
        },
    )
    row = repo.get("run-bg")
    assert row.cost_usd == pytest.approx(0.75)
    assert row.by_model["claude-sonnet-5-5"]["input_tokens"] == 120
    assert row.by_model["claude-sonnet-5-5"]["calls"] == 3
    assert row.by_model["claude-haiku-5-5"]["calls"] == 1
