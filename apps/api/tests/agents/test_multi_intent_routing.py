"""Multi-intent dispatch node — ``dispatch_next`` (MIN-65 DESIGN D4, PLAN 5.1).

Covers:
- Two queued intents run sequentially in one turn, then reflection.
- Single-intent (the common case, ``pending_flows == []``) behaves exactly as
  before this task — straight to reflection.
- Reflection's REVISE loop-back re-enters ``dispatch_next`` with an already
  empty queue, so it falls straight through to reflection again (no infinite
  loop, no re-triggering the drained secondary intent).
- The plan/HITL booking detour keeps its own topology untouched.
"""

from app.agents.graph import build_graph
from app.agents.nodes import route_tasks
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Send


def _build(structured_responses, main_responses, fast_responses):
    main = FakeLLM(structured_responses=structured_responses, responses=main_responses)
    fast = FakeLLM(responses=fast_responses)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, thread_id: str):
    return graph.invoke(
        {
            "messages": [HumanMessage(content=msg)],
            "user_id": "u1",
            "trip_id": None,
        },
        {"configurable": {"thread_id": thread_id}},
    )


def test_two_intents_run_in_parallel_then_synthesize():
    # GH-117 Path A: two intents are dispatched to parallel synthesis workers,
    # then a synthesizer combines their findings into one final answer.
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", secondary_agent="concierge")
        ],
        main_responses=["flights found", "here's what to see", "combined answer"],
        fast_responses=["OK"],
    )
    out = _invoke(
        graph, "flights to Tokyo and things to do there", thread_id="t-multi-1"
    )

    assert out["current_flow"] == "synthesize"

    # Both specialists contributed structured findings.
    agents = {r["agent"] for r in out.get("task_results", [])}
    assert agents == {"planner", "concierge"}

    # The final assistant message is the synthesized answer.
    contents = [m.content for m in out["messages"] if isinstance(m, AIMessage)]
    assert "combined answer" in contents


def test_reflection_revise_after_synthesis_re_enters_synthesize():
    # GH-117 Path A regression: when reflection REVISEs the synthesized answer,
    # it routes back via ``current_flow``. The synthesize node must set
    # ``current_flow`` to its own node name so the goto lands on a declared
    # destination; a mismatched label (the old "synthesis") is silently dropped
    # by LangGraph, the revision is wasted, and the internal revise note is left
    # as the last message in history.
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", secondary_agent="concierge")
        ],
        main_responses=[
            "flights found",
            "here's what to see",
            "synth v1",
            "synth v2",
        ],
        fast_responses=["REVISE", "OK"],
    )
    out = _invoke(
        graph, "flights to Tokyo and things to do there", thread_id="t-synth-revise"
    )

    # The revise loop actually re-ran synthesize (not silently dropped).
    assert out["current_flow"] == "synthesize"
    assert out["revisions"] == 1

    ai_contents = [m.content for m in out["messages"] if isinstance(m, AIMessage)]
    assert "synth v2" in ai_contents  # the revised answer was produced

    # The internal revise note must not be the final persisted message.
    assert not (
        isinstance(out["messages"][-1], SystemMessage)
        and "improve your previous answer" in out["messages"][-1].content
    )


def test_route_tasks_passes_parent_state_to_parallel_workers():
    # GH-117 Path A / Codex Comment 1: Send must carry the parent state because
    # LangGraph does not merge it automatically.
    state = {
        "tasks": [
            {"agent": "planner", "query": "find flights", "index": 0},
            {"agent": "concierge", "query": "check weather", "index": 1},
        ],
        "messages": [HumanMessage(content="flights and weather in Tokyo")],
        "user_id": "u1",
        "trip_id": "trip-123",
        "language": "en",
        "trip_context": "Active trip: Tokyo",
    }
    sends = route_tasks(state)
    assert len(sends) == 2
    assert all(isinstance(s, Send) and s.node == "synthesis_worker" for s in sends)
    for send, task in zip(sends, state["tasks"], strict=True):
        assert send.arg["task"] == task
        assert send.arg["messages"] == state["messages"]
        assert send.arg["user_id"] == state["user_id"]
        assert send.arg["trip_id"] == state["trip_id"]
        assert send.arg["language"] == state["language"]
        assert send.arg["trip_context"] == state["trip_context"]


def test_single_intent_goes_straight_to_reflection_unchanged():
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="concierge")],
        main_responses=["here you go"],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "what to see in Tokyo?", thread_id="t-single-1")

    assert out["current_flow"] == "concierge"
    assert out["pending_flows"] == []
    assert any("here you go" in (m.content or "") for m in out["messages"])
    # Only one sub-agent answer in the transcript — no secondary intent ran.
    ai_answers = [m.content for m in out["messages"] if m.content == "here you go"]
    assert len(ai_answers) == 1


def test_reflection_revise_loop_does_not_retrigger_drained_secondary():
    # Single intent (no secondary) so pending_flows is drained (stays []) from
    # the first dispatch_next pass; reflection then REVISEs once before
    # accepting, and dispatch_next must not re-queue anything on the replay.
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=["first draft", "revised draft"],
        fast_responses=["REVISE", "OK"],
    )
    out = _invoke(graph, "plan my trip", thread_id="t-revise-1")

    assert out["current_flow"] == "planner"
    assert out["pending_flows"] == []
    assert out["revisions"] == 1

    contents = [m.content for m in out["messages"]]
    assert "first draft" in contents
    assert "revised draft" in contents
    # Exactly one revise note was injected — the loop ran once, not forever.
    revise_notes = [
        m
        for m in out["messages"]
        if isinstance(m, SystemMessage) and "improve your previous answer" in m.content
    ]
    assert len(revise_notes) == 1


def test_booking_hitl_detour_untouched_by_dispatch():
    from langgraph.types import Command

    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="booking")],
        main_responses=["Hotel booked!"],
        fast_responses=["OK"],
    )
    cfg_thread = "t-booking-detour-1"
    first = _invoke(graph, "book me a hotel in Paris", thread_id=cfg_thread)
    assert first.get("__interrupt__"), "booking must still pause at plan_node"

    resumed = graph.invoke(
        Command(resume={"approved": True}),
        {"configurable": {"thread_id": cfg_thread}},
    )
    assert not resumed.get("__interrupt__")
    assert any("Hotel booked" in (m.content or "") for m in resumed["messages"])
    # No secondary intent was ever queued for booking — dispatch_next falls
    # straight through to reflection exactly as the old direct edge did.
    assert resumed["pending_flows"] == []


def test_task_results_cleared_between_turns():
    # GH-117 Path A regression: task_results must not leak from one turn to the
    # next. load_context_node resets them at the start of every turn.
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", secondary_agent="concierge"),
            SupervisorIntent(target_agent="concierge"),
        ],
        main_responses=[
            "flights found",
            "here's what to see",
            "combined answer",
            "sunny today",
        ],
        fast_responses=["OK", "OK"],
    )
    thread_id = "t-clear-results"
    first = _invoke(
        graph, "flights to Tokyo and things to do there", thread_id=thread_id
    )
    assert {r["agent"] for r in first.get("task_results", [])} == {
        "planner",
        "concierge",
    }

    second = _invoke(graph, "what's the weather in Tokyo?", thread_id=thread_id)
    assert second["current_flow"] == "concierge"
    # Results from the previous multi-intent turn must not survive.
    assert second.get("task_results") == []
