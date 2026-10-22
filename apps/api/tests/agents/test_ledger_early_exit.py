"""A sub-agent blocked on the traveller ends the turn via reflection's awaiting_user guard, before the judge reviews it."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.agents.graph import build_graph
from app.agents.nodes import load_context_node
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def _drive(graph, *args, **kwargs):
    """Run the graph asynchronously; synthesis_worker is an async node that a sync invoke cannot execute."""
    return asyncio.run(graph.ainvoke(*args, **kwargs))


def test_load_context_resets_awaiting_user():
    result = load_context_node(
        {"trip_id": None, "user_id": None}, SimpleNamespace(store=None)
    )
    assert result["awaiting_user"] is False
    assert result["plan_approved"] is False  # existing reset stays intact


# Graph-level: a blocked sub-agent abandons the ledger.
_CLARIFY_CALL = {
    "content": "",
    "tool_calls": [{"name": "needs_clarification", "args": {}, "id": "call-clarify-1"}],
}


def _build(structured_responses, main_responses, fast_responses):
    main = FakeLLM(structured_responses=structured_responses, responses=main_responses)
    fast = FakeLLM(responses=fast_responses)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, thread_id: str):
    return _drive(
        graph,
        {"messages": [HumanMessage(content=msg)], "user_id": "u1", "trip_id": None},
        {"configurable": {"thread_id": thread_id}},
    )


def test_blocked_single_intent_subagent_ends_cleanly():
    # Single-intent turns use the legacy static sub-agent path; a clarification
    # request sets awaiting_user and ends the turn cleanly.
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=[
            _CLARIFY_CALL,
            "Which exact date do you want to depart?",
        ],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "plan a trip at the end of this month", "t-blocked")

    assert out["awaiting_user"] is True
    assert out["current_flow"] == "planner"

    contents = [str(m.content) for m in out["messages"]]
    assert "Which exact date do you want to depart?" in contents


def test_awaiting_user_is_single_turn():
    # Turn 1 blocks on a single-intent clarification; turn 2 (same thread) runs
    # a fresh task list normally.
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner"),
            SupervisorIntent(target_agent="planner", plan=["concierge"]),
        ],
        main_responses=[
            _CLARIFY_CALL,
            "Which exact date do you want to depart?",
            "flights found",
            "weather is clear",
            "combined answer",
        ],
        fast_responses=["OK"],
    )
    out1 = _invoke(graph, "plan a trip end of this month", "t-single-turn")
    assert out1["awaiting_user"] is True

    out2 = _invoke(graph, "March 3rd", "t-single-turn")
    assert out2["awaiting_user"] is False
    contents = [str(m.content) for m in out2["messages"]]
    assert "combined answer" in contents


def test_duplicate_clarification_calls_do_not_crash():
    # A zero-arg tool invites duplicate parallel tool calls; two Commands writing
    # awaiting_user in one superstep must not InvalidUpdateError (last-write-wins reducer).
    double_call = {
        "content": "",
        "tool_calls": [
            {"name": "needs_clarification", "args": {}, "id": "call-dup-1"},
            {"name": "needs_clarification", "args": {}, "id": "call-dup-2"},
        ],
    }
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=[
            double_call,
            "Which exact date do you want to depart?",
        ],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "plan a trip end of this month", "t-dup-clarify")

    assert out["awaiting_user"] is True
    contents = [str(m.content) for m in out["messages"]]
    assert "Which exact date do you want to depart?" in contents


def test_blocked_turn_survives_revise_prone_reflection():
    # A clarifying question is by construction "incomplete", so the reflection
    # judge would flag it REVISE and re-run the sub-agent without the missing
    # detail. The awaiting_user guard must end the turn so it is not revised away.
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=[
            _CLARIFY_CALL,
            "Which exact date do you want to depart?",
        ],
        fast_responses=["REVISE"],  # reflection judge would loop if unguarded
    )
    out = _invoke(graph, "plan a trip end of this month", "t-blocked-revise")

    assert out["awaiting_user"] is True
    contents = [str(m.content) for m in out["messages"]]
    assert "Which exact date do you want to depart?" in contents
    assert not any("NEVER-RUN" in c for c in contents)


# ---------------------------------------------------------------------------
# gh-109: the flag must not depend on the model calling needs_clarification
# ---------------------------------------------------------------------------

#: An unresolvable date the numeric fast path rejects in code — no LLM call, so
#: the FakeLLM script stays deterministic.
_BAD_DATE_CALL = {
    "content": "",
    "tool_calls": [
        {
            "name": "resolve_date",
            "args": {"expression": "99/99/2026"},
            "id": "call-resolve-1",
        }
    ],
}


def test_prose_clarification_after_failed_resolve_abandons_queue():
    """gh-109: the sub-agent asks for the missing date in PROSE and never calls
    ``needs_clarification``.

    That is what shipped the duplicated reply: ``needs_clarification`` was the
    only writer of ``awaiting_user``, so the flag stayed false, the ledger
    drained, and every queued sub-agent re-answered the same question. A
    ``resolve_date`` that cannot resolve now sets the flag itself.
    """
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=[
            _BAD_DATE_CALL,
            "I need one exact date before I can search flights.",
            "NEVER-RUN concierge answer",
            "NEVER-RUN planner follow-on answer",
        ],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "plan a trip at the end of this month", "t-prose-clarify")

    assert out["awaiting_user"] is True
    contents = [str(m.content) for m in out["messages"]]
    assert "I need one exact date before I can search flights." in contents
    # The duplication: each queued sub-agent re-answering the same question.
    assert not any("NEVER-RUN" in c for c in contents)


def test_later_successful_resolve_does_not_clear_the_flag():
    """Pins an accepted trade-off: the flag is sticky within a turn.

    ``last_write_wins`` does not clear on a later success, so a model that
    retries with a *different* expression after a failure still ends the turn
    with its question. That is the intended bias — ``resolve_date``'s contract
    is "do not guess" — and the queued work is re-planned next turn anyway.
    """
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=[
            _BAD_DATE_CALL,
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "resolve_date",
                        "args": {"expression": "2026-08-30"},
                        "id": "call-resolve-2",
                    }
                ],
            },
            "Did you mean 30 August 2026?",
            "NEVER-RUN concierge answer",
        ],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "plan a trip at the end of this month", "t-sticky-flag")

    assert out["awaiting_user"] is True
    assert not any("NEVER-RUN" in str(m.content) for m in out["messages"])
