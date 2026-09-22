"""SC-11 — the background runner.

A scripted run finishes ``agent_runs.status == "completed"`` with at least one
``tool`` step and a terminal ``research_done`` bus event; a run that exceeds a tiny
``research_timeout_s`` finishes ``failed`` with ``error_type == "TimeoutError"`` and
the function itself never raises (it runs as a FastAPI ``BackgroundTask`` — awaited
directly here, so a leaked exception would surface as a test error).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from app.clients.llm import FakeLLM
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run import AgentRun
from app.repositories.agent_run import AgentRunRepository
from app.research import runner as runner_mod
from app.research.progress import ProgressBus
from app.research.runner import run_trip_research
from app.streaming.research_events import ResearchDone, ResearchError
from langgraph.store.memory import InMemoryStore

from tests.research.conftest import USER_ID, build, context


def _factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'runner.db'}"
    Base.metadata.create_all(get_engine(url))
    return get_session_factory(url)


def _seed_running_row(factory, run_id: str) -> None:
    AgentRunRepository(factory).start(
        run_id,
        user_id=USER_ID,
        conversation_id="research:u1:t1",
        thread_id="research:u1:t1",
        trip_id="t1",
        channel="research",
        kind="research",
        started_at="2020-01-01T00:00:00+00:00",
    )


def _get_run(factory, run_id: str) -> AgentRun | None:
    with factory() as s:
        return s.get(AgentRun, run_id)


def _tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"content": "", "tool_calls": [{"name": name, "args": args, "id": call_id}]}


async def _run_and_collect(bus: ProgressBus, run_id: str, **kwargs) -> list:
    """Drive the runner while a subscriber attached beforehand records every event.

    The runner now closes the channel on the terminal state (A1), so the buffer is
    gone once it returns — a subscriber that attached before the run is the honest
    way to prove the terminal event was delivered. The subscriber registers first
    (a couple of event-loop turns), so no publish is missed; ``close``'s sentinel
    ends its loop after the terminal event.
    """
    events: list = []

    async def _sub() -> None:
        async for event in bus.subscribe(run_id):
            events.append(event)

    task = asyncio.create_task(_sub())
    for _ in range(3):  # let the subscriber register its queue before we publish
        await asyncio.sleep(0)
    await run_trip_research(run_id=run_id, bus=bus, **kwargs)
    await asyncio.wait_for(task, timeout=1.0)
    return events


@pytest.mark.asyncio
async def test_scripted_run_completes_with_tool_step_and_done_event(tmp_path) -> None:
    factory = _factory(tmp_path)
    run_id = "run-ok"
    _seed_running_row(factory, run_id)

    store = InMemoryStore()
    model = FakeLLM(
        responses=[
            _tool_call(
                "write_todos",
                {"todos": [{"content": "research the trip", "status": "in_progress"}]},
                "todos",
            ),
            {"content": "dossier ready"},
        ]
    )
    agent = build(store, llm=model, grader=FakeLLM(responses=[{"content": "ok"}]))
    bus = ProgressBus()

    events = await _run_and_collect(
        bus,
        run_id,
        ctx=context(),
        instruction="research my trip in depth",
        agent=agent,
        session_factory=factory,
    )

    row = _get_run(factory, run_id)
    assert row is not None
    assert row.status == "completed"

    steps = AgentRunRepository(factory).steps_for(run_id)
    assert any(step.kind == "tool" for step in steps)

    assert any(isinstance(e, ResearchDone) and e.status == "completed" for e in events)
    # A1: the channel is released once the run is terminal.
    assert bus.has(run_id) is False


@pytest.mark.asyncio
async def test_timeout_finishes_failed_and_never_raises(tmp_path, monkeypatch) -> None:
    factory = _factory(tmp_path)
    run_id = "run-timeout"
    _seed_running_row(factory, run_id)

    # A tiny timeout; the stub agent's stream sleeps well past it.
    monkeypatch.setattr(
        runner_mod,
        "get_settings",
        lambda: SimpleNamespace(research_timeout_s=0.01),
    )

    async def _never():  # pragma: no cover - never reached (timeout fires first)
        return
        yield

    class _SleepAgent:
        store = InMemoryStore()

        async def astream_events(self, inp, config=None, *, version, context=None):
            await asyncio.sleep(0.5)
            return _never()

    bus = ProgressBus()

    # Must return normally, not raise, even though the run times out.
    events = await _run_and_collect(
        bus,
        run_id,
        ctx=context(),
        instruction="research",
        agent=_SleepAgent(),
        session_factory=factory,
    )

    row = _get_run(factory, run_id)
    assert row is not None
    assert row.status == "failed"

    steps = AgentRunRepository(factory).steps_for(run_id)
    assert any(step.error_type == "TimeoutError" for step in steps)

    assert any(
        isinstance(e, ResearchError) and e.code == "TimeoutError" for e in events
    )
    # A1: the channel is released even on the failure path.
    assert bus.has(run_id) is False


@pytest.mark.parametrize(
    ("language", "name"),
    [("vi", "Vietnamese"), ("en", "English"), ("xx", "English")],
)
def test_turn_input_names_the_travellers_language(language, name) -> None:
    """The model never sees ``state['language']`` (only tools read it), so the turn
    message itself names the language the dossier and summary are written in."""
    from dataclasses import replace

    ctx = replace(context(), language=language)
    for instruction in (None, "add more street food"):
        content = runner_mod._build_input(ctx, instruction)["messages"][0].content
        assert content.endswith(f"Language: {name}")


def _grade(result: str, passed: bool) -> dict:
    from deepagents.middleware.rubric import GraderResponse

    criterion = {"name": "The proposal passes validate_proposal", "passed": passed}
    if not passed:
        criterion["gap"] = "no place, hotel or offer ids"
    return {
        "content": "",
        "tool_calls": [
            {
                "name": GraderResponse.__name__,
                "args": {
                    "result": result,
                    "explanation": f"proposal {result}",
                    "criteria": [criterion],
                },
                "id": f"grade-{result}",
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("grades", "rubric_status"),
    [
        ([_grade("satisfied", True)], "satisfied"),
        (
            [_grade("needs_revision", False), _grade("needs_revision", False)],
            "max_iterations_reached",
        ),
    ],
    ids=["satisfied", "rejected"],
)
async def test_the_grader_verdict_is_recorded_on_a_terminal_step(
    tmp_path,
    grades,
    rubric_status,
) -> None:
    """research-proposal-validity: a run the grader never accepted still finishes
    ``completed`` (the dossier exists) but its verdict is durable, so the chat and
    the card can say "needs review" instead of "done"."""
    factory = _factory(tmp_path)
    run_id = f"run-{rubric_status}"
    _seed_running_row(factory, run_id)
    model = FakeLLM(responses=[{"content": "dossier ready"}, {"content": "revised"}])
    agent = build(InMemoryStore(), llm=model, grader=FakeLLM(responses=grades))

    await _run_and_collect(
        ProgressBus(),
        run_id,
        ctx=context(),
        instruction="research my trip in depth",
        agent=agent,
        session_factory=factory,
    )

    assert _get_run(factory, run_id).status == "completed"
    rubric = [
        s for s in AgentRunRepository(factory).steps_for(run_id) if s.node == "rubric"
    ]
    assert [s.meta for s in rubric] == [{"rubric_status": rubric_status}]


def test_turn_input_names_the_departure_point_when_known() -> None:
    from dataclasses import replace

    ctx = replace(context(), origin="Ho Chi Minh City")
    content = runner_mod._build_input(ctx, None)["messages"][0].content
    assert content.endswith("Departing from: Ho Chi Minh City\nLanguage: English")

    content = runner_mod._build_input(context(), None)["messages"][0].content
    assert "Departing from" not in content
