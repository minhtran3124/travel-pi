"""Chat node ``research`` (trip-research-deep-agent, Task 6.1, SC-18).

The launcher makes **no** LLM call: the supervisor already routed the intent. It
books a background run through ``ResearchService.start`` and then *schedules* the
run's driver as an ``asyncio`` task so the dossier actually gets produced — the bug
this suite guards is a booked ``running`` row that nothing ever executes. The node
is async because it runs on the event loop (an async graph node) and must launch
the driver without awaiting it; the chat turn returns immediately.

Most tests drive the node function directly with a stub service factory, so nothing
touches the DB or the network. ``language=None`` keeps ``system_reply`` on the
English source (no translation store lookup). The free-tier guarantee is enforced
one step earlier, by the supervisor's ``allowed_subagents`` gate (research is
premium-only), so the node is never reached — asserted here against the real
supervisor.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.constants import (
    RESEARCH_COMPLETED_MSG,
    RESEARCH_IN_PROGRESS_MSG,
    RESEARCH_LIMIT_REACHED_MSG,
    RESEARCH_NEEDS_TRIP_MSG,
    RESEARCH_STARTED_MSG,
    RESEARCH_UNAVAILABLE_MSG,
)
from app.agents.context import AgentContext, resolve_agent_context
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run import AgentRun
from app.db.models.trip import Trip
from app.enums import Tier
from app.exceptions import ConflictError, RateLimitError
from app.research import launcher, runtime
from app.research import runner as runner_mod
from app.research.launcher import make_research_node
from app.research.progress import ProgressBus
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.store.memory import InMemoryStore

OWNER = "u_research"
TRIP = "trip-1"


@pytest.fixture(autouse=True)
def _reset_runtime_and_tasks():
    """Keep the process-level research runtime holder and the launcher's task set
    hermetic between tests (both are module globals)."""
    runtime.set_research_runtime(None, None)
    launcher._BACKGROUND_TASKS.clear()
    yield
    launcher._BACKGROUND_TASKS.clear()
    runtime.set_research_runtime(None, None)


def _flag(monkeypatch, *, enabled: bool, database_url: str | None = None) -> None:
    """Point the launcher's settings read at a fixed ``research_enabled`` (and, for
    the paths that build a real service, a ``database_url``)."""
    monkeypatch.setattr(
        launcher,
        "get_settings",
        lambda: SimpleNamespace(research_enabled=enabled, database_url=database_url),
    )


def _state(**overrides) -> dict:
    state = {
        "messages": [HumanMessage(content="research my whole trip in depth")],
        "user_id": OWNER,
        "trip_id": TRIP,
        "language": None,
    }
    state.update(overrides)
    return state


def _service_factory() -> tuple[MagicMock, MagicMock]:
    """A stub ``ResearchService`` (``runnable`` true, ``launch`` an AsyncMock so the
    node can schedule it) whose ``start`` records its calls, and a factory returning
    it. The factory is a MagicMock so "never constructed" is provable, not just
    "start never called"."""
    service = MagicMock(name="ResearchService")
    service.runnable = True
    service.launch = AsyncMock(name="launch")
    factory = MagicMock(name="service_factory", return_value=service)
    return service, factory


async def _drain() -> None:
    """Await every driver the node scheduled this turn (so an AsyncMock coroutine is
    never left un-awaited)."""
    await asyncio.gather(*list(launcher._BACKGROUND_TASKS))


# -- flag off -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_off_replies_unavailable_and_never_touches_the_service(monkeypatch):
    _flag(monkeypatch, enabled=False)
    service, factory = _service_factory()

    result = await make_research_node(factory)(_state())

    assert result["messages"][0].content == RESEARCH_UNAVAILABLE_MSG
    assert "current_flow" not in result
    assert not result.get("awaiting_user")
    factory.assert_not_called()
    service.start.assert_not_called()
    service.launch.assert_not_called()


# -- no active trip -----------------------------------------------------------


@pytest.mark.asyncio
async def test_no_trip_asks_the_traveller_and_never_starts(monkeypatch):
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()

    result = await make_research_node(factory)(_state(trip_id=None))

    assert result["awaiting_user"] is True
    assert result["messages"][0].content == RESEARCH_NEEDS_TRIP_MSG
    factory.assert_not_called()
    service.start.assert_not_called()


@pytest.mark.asyncio
async def test_empty_string_trip_is_treated_as_no_trip(monkeypatch):
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()

    result = await make_research_node(factory)(_state(trip_id=""))

    assert result["awaiting_user"] is True
    service.start.assert_not_called()


# -- premium + trip: exactly one job -----------------------------------------


@pytest.mark.asyncio
async def test_premium_with_trip_starts_and_schedules_exactly_one_job(monkeypatch):
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()

    result = await make_research_node(factory)(_state())

    service.start.assert_called_once_with(OWNER, TRIP)
    # The booked run is actually scheduled for execution — exactly once, keyed to the
    # run id ``start`` returned. This is the regression guard: booking is not enough.
    service.launch.assert_called_once_with(
        service.start.return_value, OWNER, TRIP, language=None
    )
    assert len(launcher._BACKGROUND_TASKS) == 1

    assert result["current_flow"] == "research"
    msg = result["messages"][0]
    assert isinstance(msg, AIMessage)
    assert msg.content == RESEARCH_STARTED_MSG
    # The guard flag reflection reads to end the turn (no second job on a REVISE).
    assert msg.additional_kwargs.get("research_started") is True

    await _drain()


@pytest.mark.asyncio
async def test_already_running_is_reassured_and_schedules_no_second_driver(monkeypatch):
    """A ConflictError (a run is already in flight) is not a 500: reply with the same
    'started' copy and set the guard — and, since a driver already owns that thread,
    do NOT schedule a second one."""
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()
    service.start.side_effect = ConflictError("already running")

    result = await make_research_node(factory)(_state())

    service.start.assert_called_once_with(OWNER, TRIP)
    service.launch.assert_not_called()
    assert set() == launcher._BACKGROUND_TASKS
    msg = result["messages"][0]
    assert msg.content == RESEARCH_STARTED_MSG
    assert msg.additional_kwargs.get("research_started") is True
    assert result["current_flow"] == "research"


@pytest.mark.asyncio
async def test_daily_cap_reached_says_so_and_schedules_no_driver(monkeypatch):
    """The chat path spends the same daily cap as the REST start. Over it, the
    traveller is told why — not the generic error copy — and nothing is scheduled."""
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()
    service.start.side_effect = RateLimitError(retry_after=60)

    result = await make_research_node(factory)(_state())

    service.launch.assert_not_called()
    assert set() == launcher._BACKGROUND_TASKS
    msg = result["messages"][0]
    assert msg.content == RESEARCH_LIMIT_REACHED_MSG
    assert "research_started" not in msg.additional_kwargs


# -- existing run: answer its status, book nothing ----------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "copy"),
    [
        ("completed", RESEARCH_COMPLETED_MSG),
        ("running", RESEARCH_IN_PROGRESS_MSG),
    ],
)
async def test_existing_run_replies_its_status_and_books_nothing(
    monkeypatch,
    state,
    copy,
):
    """A trip whose latest run finished or is live here gets its status, not a new
    run: a chat re-run carries no instruction, so it would only spend the daily cap
    on an empty revise and reply 'started' again."""
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()
    service.chat_state.return_value = state
    service.completed_summary.return_value = None

    result = await make_research_node(factory)(
        _state(messages=[HumanMessage(content="bạn chạy research xong chưa?")])
    )

    service.chat_state.assert_called_once_with(OWNER, TRIP)
    service.start.assert_not_called()
    service.launch.assert_not_called()
    assert result["current_flow"] == "research"
    msg = result["messages"][0]
    assert msg.content == copy
    assert msg.additional_kwargs.get("research_status") == state
    assert "research_started" not in msg.additional_kwargs


@pytest.mark.asyncio
async def test_chat_launch_runs_in_the_chat_language(monkeypatch):
    """The dossier and its summary follow the traveller's chat language."""
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()

    await make_research_node(factory)(_state(language="vi"))
    await _drain()

    service.launch.assert_called_once_with(
        service.start.return_value, OWNER, TRIP, language="vi"
    )


@pytest.mark.asyncio
async def test_completed_reply_carries_the_research_summary(monkeypatch):
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()
    service.chat_state.return_value = "completed"
    service.completed_summary.return_value = "- Cheapest flight 1.2M VND\n- Stay in Duong Dong"

    result = await make_research_node(factory)(_state())

    service.completed_summary.assert_called_once_with(OWNER, TRIP)
    assert result["messages"][0].content == (
        f"{RESEARCH_COMPLETED_MSG}\n\n- Cheapest flight 1.2M VND\n- Stay in Duong Dong"
    )
    service.start.assert_not_called()


def _seed_run(url: str, *, status: str, user_id: str = OWNER) -> None:
    with get_session_factory(url)() as s:
        s.add(
            AgentRun(
                user_id=user_id,
                conversation_id="research:x",
                thread_id="research:x",
                trip_id=TRIP,
                channel="research",
                kind="research",
                status=status,
            )
        )
        s.commit()


def _real_service_db(monkeypatch, tmp_path, name: str) -> str:
    url = f"sqlite:///{tmp_path / name}"
    Base.metadata.create_all(get_engine(url))
    with get_session_factory(url)() as s:
        s.add(Trip(id=TRIP, user_id=OWNER, title="Trip", travelers=2))
        s.commit()
    _flag(monkeypatch, enabled=True, database_url=url)
    runtime.set_research_runtime(SimpleNamespace(store=InMemoryStore()), ProgressBus())

    async def fake_runner(**kwargs):
        return None

    monkeypatch.setattr(runner_mod, "run_trip_research", fake_runner)
    return url


@pytest.mark.asyncio
async def test_completed_run_on_the_real_service_books_no_second_run(
    monkeypatch,
    tmp_path,
):
    url = _real_service_db(monkeypatch, tmp_path, "done.db")
    _seed_run(url, status="completed")

    store = InMemoryStore()
    node = make_research_node(lambda: launcher.build_research_service(store))
    result = await node(_state())

    # An older dossier with no summary.md: the copy alone, never an error.
    assert result["messages"][0].content == RESEARCH_COMPLETED_MSG

    service = launcher.build_research_service(store)
    service.write_file(service.latest(TRIP).id, "/research/summary.md", "- Two easy days")
    result = await node(_state())

    assert result["messages"][0].content == f"{RESEARCH_COMPLETED_MSG}\n\n- Two easy days"
    with get_session_factory(url)() as s:
        assert s.query(AgentRun).count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "interrupted"])
async def test_failed_run_on_the_real_service_starts_a_new_one(
    monkeypatch,
    tmp_path,
    status,
):
    url = _real_service_db(monkeypatch, tmp_path, f"{status}.db")
    _seed_run(url, status=status)

    node = make_research_node(lambda: launcher.build_research_service(InMemoryStore()))
    result = await node(_state())
    await _drain()

    assert result["messages"][0].content == RESEARCH_STARTED_MSG
    with get_session_factory(url)() as s:
        assert s.query(AgentRun).count() == 2


@pytest.mark.asyncio
async def test_another_users_completed_run_does_not_answer_for_this_user(
    monkeypatch,
    tmp_path,
):
    url = _real_service_db(monkeypatch, tmp_path, "other.db")
    _seed_run(url, status="completed", user_id="someone-else")

    node = make_research_node(lambda: launcher.build_research_service(InMemoryStore()))
    result = await node(_state())
    await _drain()

    assert result["messages"][0].content == RESEARCH_STARTED_MSG


# -- runtime holds no agent: decline, book nothing ---------------------------


@pytest.mark.asyncio
async def test_no_built_agent_replies_unavailable_and_inserts_no_run(
    monkeypatch, tmp_path
):
    """Flag on but the runtime holds no agent (build failed): the node must decline
    with ``research_unavailable`` and leave the DB untouched — booking a row nothing
    can execute is the defect. Exercises the real ``build_research_service`` path."""
    url = f"sqlite:///{tmp_path / 'noagent.db'}"
    Base.metadata.create_all(get_engine(url))
    with get_session_factory(url)() as s:
        s.add(Trip(id=TRIP, user_id=OWNER, title="Trip", travelers=2))
        s.commit()
    _flag(monkeypatch, enabled=True, database_url=url)
    runtime.set_research_runtime(None, None)  # explicit: build failed / flag-off holder

    store = InMemoryStore()
    node = make_research_node(lambda: launcher.build_research_service(store))
    result = await node(_state())

    assert result["messages"][0].content == RESEARCH_UNAVAILABLE_MSG
    assert "current_flow" not in result
    with get_session_factory(url)() as s:
        assert s.query(AgentRun).count() == 0


# -- end to end: booked run is actually executed by the runner ----------------


@pytest.mark.asyncio
async def test_chat_entry_books_and_executes_one_run(monkeypatch, tmp_path):
    """A premium chat turn on an active trip books a run AND drives it: the runner is
    invoked exactly once, for the booked run id, on the agent/bus from the runtime
    holder. Proves the run is executed, not merely booked. Uses the real service and
    launcher wiring with a fake agent injected through the runtime holder and the
    runner faked so no LLM/network is touched."""
    url = f"sqlite:///{tmp_path / 'exec.db'}"
    Base.metadata.create_all(get_engine(url))
    with get_session_factory(url)() as s:
        s.add(Trip(id=TRIP, user_id=OWNER, title="Trip", travelers=2))
        s.commit()
    _flag(monkeypatch, enabled=True, database_url=url)

    fake_agent = SimpleNamespace(store=InMemoryStore())
    fake_bus = ProgressBus()
    runtime.set_research_runtime(fake_agent, fake_bus)

    calls: list[dict] = []

    async def fake_runner(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(runner_mod, "run_trip_research", fake_runner)

    store = InMemoryStore()
    node = make_research_node(lambda: launcher.build_research_service(store))
    result = await node(_state())

    assert result["current_flow"] == "research"
    # The row is booked ``running`` before the driver runs.
    with get_session_factory(url)() as s:
        booked = s.query(AgentRun).all()
        assert len(booked) == 1
        run_id = booked[0].id
        assert booked[0].status == "running"

    await _drain()

    assert len(calls) == 1, "the runner must be invoked exactly once"
    assert calls[0]["run_id"] == run_id, "the executed run is the booked run"
    assert calls[0]["agent"] is fake_agent
    assert calls[0]["bus"] is fake_bus
    assert calls[0]["resumed_from"] is None


@pytest.mark.asyncio
async def test_node_returns_without_awaiting_the_run(monkeypatch, tmp_path):
    """The chat turn must not block on the run. With a driver that never completes,
    the node still returns its 'started' reply promptly and the driver stays pending."""
    url = f"sqlite:///{tmp_path / 'nowait.db'}"
    Base.metadata.create_all(get_engine(url))
    with get_session_factory(url)() as s:
        s.add(Trip(id=TRIP, user_id=OWNER, title="Trip", travelers=2))
        s.commit()
    _flag(monkeypatch, enabled=True, database_url=url)

    runtime.set_research_runtime(SimpleNamespace(store=InMemoryStore()), ProgressBus())

    never = asyncio.Event()

    async def blocking_runner(**kwargs):
        await never.wait()

    monkeypatch.setattr(runner_mod, "run_trip_research", blocking_runner)

    store = InMemoryStore()
    node = make_research_node(lambda: launcher.build_research_service(store))

    result = await asyncio.wait_for(node(_state()), timeout=1.0)

    assert result["current_flow"] == "research"
    assert result["messages"][0].content == RESEARCH_STARTED_MSG
    # The driver is still running — the node did not await it.
    assert len(launcher._BACKGROUND_TASKS) == 1
    assert not next(iter(launcher._BACKGROUND_TASKS)).done()

    # Cleanup: release and drain so no task is left pending at teardown.
    never.set()
    await _drain()


# -- free tier: gated at the supervisor, node never reached -------------------


def _runtime(ctx: AgentContext) -> SimpleNamespace:
    return SimpleNamespace(context=ctx)


def test_free_tier_gets_the_premium_notice_and_no_job_starts(monkeypatch):
    """research is premium-only: the free tier is degraded by the supervisor's
    allowed_subagents gate before ever reaching the launcher, so no job starts."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    # Guard: if the launcher were ever reached, start would raise.
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()
    service.start.side_effect = AssertionError("launcher must not run on free tier")

    ctx = resolve_agent_context(tier=Tier.FREE)
    assert "research" not in (ctx.allowed_subagents or frozenset())

    supervisor = make_supervisor(
        FakeLLM(structured_responses=[SupervisorIntent(target_agent="research")])
    )
    cmd = supervisor(
        {"messages": [HumanMessage(content="research my whole trip in depth")]},
        _runtime(ctx),
    )

    # Degraded to the code-authored upgrade notice; no tasks, so route_tasks never
    # dispatches the research node.
    assert "tasks" not in cmd.update
    assert cmd.update["messages"][0].content
    service.start.assert_not_called()
    factory.assert_not_called()
