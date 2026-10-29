"""Live registry + callback handler: phases from recorded events, parallel specialists,
cleanup on success/error/cancel, size caps, no leaked text/ids, and no DB writes."""

import asyncio
import json
from uuid import uuid4

import pytest
from app.agents import live_registry as lr
from app.agents.graph import build_graph
from app.agents.live_registry import LiveRegistry, LiveTurnHandler
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core import heartbeat as hb
from app.db.engine import get_engine
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from sqlalchemy import event

RUN = "0f3c9a1e-aaaa-bbbb-cccc-1234567890ab"
CONV = "9d8e7f6a-1111-2222-3333-444455556666"


@pytest.fixture
def reg():
    return LiveRegistry()


@pytest.fixture
def handler(reg):
    return LiveTurnHandler(RUN, conv=CONV, kind="chat", live=reg)


def _agents(reg):
    turns = reg.snapshot()["turns"]
    return [(a["agent"], a["phase"], a["tool"]) for t in turns for a in t["agents"]]


def _node(handler, node, ns=None, *, root=None, **extra):
    rid = uuid4()
    handler.on_chain_start(
        {},
        {},
        run_id=rid,
        parent_run_id=root or uuid4(),
        metadata={
            "langgraph_node": node,
            "langgraph_checkpoint_ns": ns or f"{node}:{rid}",
            **extra,
        },
    )
    return rid


def _root(handler):
    rid = uuid4()
    handler.on_chain_start({}, {}, run_id=rid, parent_run_id=None, metadata={})
    return rid


def test_phases_follow_the_graph(reg, handler):
    root = _root(handler)
    guard = _node(handler, "pii_guardrail")
    assert _agents(reg) == [("supervisor", "classify", None)]
    handler.on_chain_end({}, run_id=guard, parent_run_id=root)
    sup = _node(handler, "supervisor")
    assert _agents(reg) == [("supervisor", "classify", None)]
    handler.on_chain_end({}, run_id=sup, parent_run_id=root)
    assert _agents(reg) == []

    ns = "planner:abc"
    planner = _node(handler, "planner", ns)
    assert _agents(reg) == [("planner", "specialist", None)]
    # sub-graph re-emits the parent's start, and inner nodes must not add agents
    _node(handler, "planner", ns)
    _node(handler, "assistant", f"{ns}|assistant:xyz")
    assert _agents(reg) == [("planner", "specialist", None)]

    tool = uuid4()
    handler.on_tool_start(
        {"name": "search_flights"},
        "SECRET ARGS",
        run_id=tool,
        metadata={
            "langgraph_node": "tools",
            "langgraph_checkpoint_ns": f"{ns}|tools:q",
        },
    )
    assert _agents(reg) == [("planner", "tools", "search_flights")]
    handler.on_tool_end("SECRET OUTPUT", run_id=tool)
    assert _agents(reg) == [("planner", "specialist", None)]

    handler.on_chain_end({}, run_id=planner, parent_run_id=root)
    refl = _node(handler, "reflection")
    assert _agents(reg) == [("supervisor", "reflection", None)]
    handler.on_chain_end({}, run_id=refl, parent_run_id=root)
    handler.on_chain_end({}, run_id=root, parent_run_id=None)
    assert reg.snapshot() == {"turns": []}


def test_two_parallel_specialists_via_synthesis_workers(reg, handler):
    _root(handler)
    ns_a, ns_b = "synthesis_worker:a1", "synthesis_worker:b2"
    _node(handler, "synthesis_worker", ns_a)
    _node(handler, "synthesis_worker", ns_b)
    assert sorted(a for a, _, _ in _agents(reg)) == ["specialist", "specialist"]
    # identity arrives on the inner events through the specialist metadata
    _node(handler, "assistant", f"{ns_a}|assistant:1", specialist="planner")
    _node(handler, "assistant", f"{ns_b}|assistant:2", specialist="concierge")
    assert sorted(a for a, _, _ in _agents(reg)) == ["concierge", "planner"]
    tool = uuid4()
    handler.on_tool_start(
        {"name": "get_weather"},
        "",
        run_id=tool,
        metadata={
            "langgraph_node": "tools",
            "langgraph_checkpoint_ns": f"{ns_b}|tools:3",
            "specialist": "concierge",
        },
    )
    by_agent = {a: (p, t) for a, p, t in _agents(reg)}
    assert by_agent == {
        "planner": ("specialist", None),
        "concierge": ("tools", "get_weather"),
    }


def test_unknown_specialist_name_is_not_echoed(reg, handler):
    _root(handler)
    ns = "synthesis_worker:z"
    _node(handler, "synthesis_worker", ns)
    _node(handler, "assistant", f"{ns}|assistant:1", specialist="user typed this")
    assert _agents(reg) == [("specialist", "specialist", None)]


def test_turn_removed_when_root_errors(reg, handler):
    root = _root(handler)
    _node(handler, "planner")
    assert reg.snapshot()["turns"]
    handler.on_chain_error(asyncio.CancelledError(), run_id=root, parent_run_id=None)
    assert reg.snapshot() == {"turns": []}
    # later stray events do not resurrect it
    _node(handler, "planner")
    assert reg.snapshot() == {"turns": []}


def test_finish_is_the_cancel_backstop(reg, handler):
    _root(handler)
    _node(handler, "concierge")
    handler.finish()
    handler.finish()
    assert reg.snapshot() == {"turns": []}


def test_snapshot_caps(reg):
    for i in range(lr.MAX_TURNS + 10):
        reg.start_turn(f"run-{i:04d}-xxxxxxxx", "c", "chat")
    assert len(reg.snapshot()["turns"]) == lr.MAX_TURNS
    reg.start_turn("agents", "c", "chat")
    for i in range(lr.MAX_AGENTS_PER_TURN + 5):
        reg.set_agent("agents", f"k{i}", "planner", "specialist")
    turn = next(t for t in reg.snapshot()["turns"] if t["run_id"] == "agents")
    assert len(turn["agents"]) == lr.MAX_AGENTS_PER_TURN


def test_stale_turns_are_evicted(reg, monkeypatch):
    reg.start_turn("old", "c", "chat")
    base = lr.time.monotonic()
    monkeypatch.setattr(
        lr.time, "monotonic", lambda: base + lr.MAX_TURN_AGE_SECONDS + 1
    )
    assert reg.snapshot() == {"turns": []}


def test_snapshot_has_no_text_or_full_ids(reg, handler):
    _root(handler)
    _node(handler, "planner")
    tool = uuid4()
    handler.on_tool_start(
        {"name": "search_flights"},
        "my passport is X123 and email a@b.co",
        run_id=tool,
        metadata={
            "langgraph_node": "tools",
            "langgraph_checkpoint_ns": "planner:1|tools:2",
        },
    )
    raw = json.dumps(reg.snapshot())
    assert "passport" not in raw and "a@b.co" not in raw
    assert RUN not in raw and CONV not in raw
    turn = reg.snapshot()["turns"][0]
    assert turn["run_id"] == RUN[:8] and turn["conv"] == CONV[:6]
    assert set(turn) == {"run_id", "conv", "kind", "started_at", "agents"}
    assert set(turn["agents"][0]) == {"agent", "phase", "tool", "since"}


def test_hooks_never_raise(reg, handler):
    handler.on_chain_start({}, {}, run_id=uuid4(), parent_run_id=None, metadata=None)
    handler.on_tool_start(None, "", run_id=uuid4(), metadata=None)
    handler.on_tool_end(None, run_id=uuid4())
    handler.on_chain_end(None, run_id=uuid4(), parent_run_id=None)


def test_handler_performs_no_db_writes(tmp_db, reg, handler):
    engine = get_engine(tmp_db)
    statements = []

    def spy(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", spy)
    try:
        root = _root(handler)
        planner = _node(handler, "planner")
        tool = uuid4()
        handler.on_tool_start(
            {"name": "t"},
            "",
            run_id=tool,
            metadata={
                "langgraph_node": "tools",
                "langgraph_checkpoint_ns": "planner:1|tools:2",
            },
        )
        handler.on_tool_end("", run_id=tool)
        handler.on_chain_end({}, run_id=planner, parent_run_id=root)
        handler.on_chain_end({}, run_id=root, parent_run_id=None)
        reg.snapshot()
    finally:
        event.remove(engine, "before_cursor_execute", spy)
    assert statements == []


def test_registry_snapshot_is_the_heartbeat_provider():
    lr.registry.clear()
    lr.registry.start_turn("rrrrrrrr-1", "cccccc", "chat")
    hb.set_snapshot_provider(lr.registry.snapshot)
    try:
        assert hb._snapshot_provider()["turns"][0]["run_id"] == "rrrrrrrr"
    finally:
        hb.set_snapshot_provider(None)
        lr.registry.clear()


def test_real_multi_intent_turn_shows_both_specialists_then_clears(reg):
    """Drives the real graph with FakeLLM so node names and the specialist metadata are checked live."""
    seen: set[str] = set()

    class Spy(LiveRegistry):
        def set_agent(self, run_id, key, agent, phase, tool=None):
            super().set_agent(run_id, key, agent, phase, tool)

        def rename_agent(self, run_id, key, name):
            super().rename_agent(run_id, key, name)
            seen.add(name)

        def snapshot(self):
            snap = super().snapshot()
            for t in snap["turns"]:
                seen.update(a["agent"] for a in t["agents"])
            return snap

    spy = Spy()
    main = FakeLLM(
        structured_responses=[
            SupervisorIntent(target_agent="planner", plan=["concierge"])
        ],
        responses=["flights found", "here's what to see", "combined answer"],
    )
    graph = build_graph(
        llm=main,
        fast_llm=FakeLLM(responses=["OK"]),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )
    live = LiveTurnHandler(RUN, conv=CONV, kind="chat", live=spy)

    async def drive():
        task = asyncio.create_task(
            graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(content="flights to Tokyo and things to do")
                    ],
                    "user_id": "u1",
                    "trip_id": None,
                },
                {"configurable": {"thread_id": "t-live"}, "callbacks": [live]},
            )
        )
        while not task.done():
            spy.snapshot()
            await asyncio.sleep(0)
        await task

    asyncio.run(drive())
    assert {"planner", "concierge"} <= seen
    assert spy.snapshot() == {"turns": []}
