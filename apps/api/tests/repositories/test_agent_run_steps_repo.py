"""AgentRunRepository step storage: add_steps / steps_for / finish prompt_versions."""

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import AgentRun, AgentRunStep
from app.repositories.agent_run import AgentRunRepository


@pytest.fixture
def repo(tmp_db):
    factory = get_session_factory(tmp_db)
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    with factory() as s:
        s.query(AgentRunStep).delete()
        s.query(AgentRun).delete()
        s.commit()
    return AgentRunRepository(factory)


def _start(repo, id="run-1"):
    repo.start(
        id,
        user_id="u1",
        conversation_id="c1",
        thread_id="t1",
        trip_id=None,
        channel="chat",
        kind="turn",
        started_at="2026-09-03T00:00:00+00:00",
    )


def test_add_steps_then_steps_for_returns_seq_order(repo):
    _start(repo)
    # Inserted out of order — the read must still come back by ``seq``.
    repo.add_steps(
        "run-1",
        [
            {"seq": 2, "kind": "llm", "status": "ok", "model": "gpt-5", "ms": 300},
            {"seq": 0, "kind": "node", "status": "ok", "node": "supervisor"},
            {"seq": 1, "kind": "tool", "status": "error", "tool_name": "search_hotels"},
        ],
    )
    steps = repo.steps_for("run-1")
    assert [s.seq for s in steps] == [0, 1, 2]
    assert [s.kind for s in steps] == ["node", "tool", "llm"]
    assert steps[1].tool_name == "search_hotels"
    assert steps[1].status == "error"
    assert steps[2].model == "gpt-5"
    assert steps[2].ms == 300
    # Column defaults apply to keys the payload omitted.
    assert steps[0].input_tokens == 0
    assert steps[0].offset_ms == 0


def test_add_steps_ignores_unknown_keys(repo):
    _start(repo)
    repo.add_steps(
        "run-1",
        [
            {
                "seq": 0,
                "kind": "llm",
                "status": "ok",
                "meta": {"finish_reason": "stop"},
                "total_tokens": 140,  # derivable, not a column → ignored
                "bogus": "x",  # ignored
            }
        ],
    )
    step = repo.steps_for("run-1")[0]
    assert step.meta == {"finish_reason": "stop"}
    assert not hasattr(step, "bogus")


def test_add_steps_empty_list_is_noop(repo):
    _start(repo)
    repo.add_steps("run-1", [])
    assert repo.steps_for("run-1") == []


def test_add_steps_missing_run_does_not_raise(repo):
    # Steps are supplementary: a write for an unknown run must never raise.
    repo.add_steps("nope", [{"seq": 0, "kind": "node", "status": "ok"}])
    assert [s.seq for s in repo.steps_for("nope")] == [0]


def test_steps_for_scopes_to_run(repo):
    _start(repo, id="run-a")
    _start(repo, id="run-b")
    repo.add_steps("run-a", [{"seq": 0, "kind": "node", "status": "ok"}])
    repo.add_steps("run-b", [{"seq": 0, "kind": "llm", "status": "ok"}])
    assert [s.kind for s in repo.steps_for("run-a")] == ["node"]
    assert [s.kind for s in repo.steps_for("run-b")] == ["llm"]


def test_finish_records_prompt_versions(repo):
    _start(repo)
    repo.finish(
        "run-1",
        status="completed",
        current_flow=None,
        finished_at="2026-09-03T00:00:05+00:00",
        metrics={"llm_calls": 1},
        prompt_versions=[{"name": "communication_style", "version": 9}],
    )
    assert repo.list_recent()[0].prompt_versions == [
        {"name": "communication_style", "version": 9}
    ]


def test_finish_without_prompt_versions_leaves_value_unchanged(repo):
    _start(repo)
    repo.finish(
        "run-1",
        status="completed",
        current_flow=None,
        finished_at="2026-09-03T00:00:05+00:00",
        metrics={"llm_calls": 1},
        prompt_versions=[{"name": "supervisor", "version": 2}],
    )
    repo.finish(
        "run-1",
        status="completed",
        current_flow=None,
        finished_at="2026-09-03T00:00:06+00:00",
        metrics={"llm_calls": 2},
    )
    assert repo.list_recent()[0].prompt_versions == [
        {"name": "supervisor", "version": 2}
    ]
