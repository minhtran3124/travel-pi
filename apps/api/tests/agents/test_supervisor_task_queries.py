"""Supervisor per-task queries (specs/specialist-task-description Task 1.1).

``SupervisorIntent.task_queries`` carries one self-contained restatement per
specialist in ``[target_agent, *plan]`` order. The supervisor aligns those to
the emitted tasks by agent name and falls back to the last user message for
any missing, blank, short or mis-aligned entry.

Direct supervisor calls with a FakeLLM structured response (the pattern in
``test_supervisor_plan_semantics.py``).
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.context import AgentContext
from app.agents.supervisor import SupervisorIntent, make_supervisor
from app.clients.llm import FakeLLM
from langchain_core.messages import HumanMessage

USER_MESSAGE = "find flights to Hanoi and tell me where to eat pho"


def _tasks_for(intent: SupervisorIntent) -> list[dict]:
    supervisor = make_supervisor(FakeLLM(structured_responses=[intent]))
    cmd = supervisor(
        {"messages": [HumanMessage(content=USER_MESSAGE)]},
        SimpleNamespace(context=AgentContext()),
    )
    return cmd.update["tasks"]


def _queries(tasks: list[dict]) -> list[tuple[str, str]]:
    return [(t["agent"], t["query"]) for t in tasks]


def test_distinct_query_per_task():
    tasks = _tasks_for(
        SupervisorIntent(
            target_agent="planner",
            plan=["concierge"],
            task_queries=["find flights to Hanoi", "where to eat pho in Hanoi"],
        )
    )
    assert _queries(tasks) == [
        ("planner", "find flights to Hanoi"),
        ("concierge", "where to eat pho in Hanoi"),
    ]
    assert [t["index"] for t in tasks] == [0, 1]


def test_fallback_when_task_queries_missing():
    tasks = _tasks_for(SupervisorIntent(target_agent="planner", plan=["concierge"]))
    assert _queries(tasks) == [
        ("planner", USER_MESSAGE),
        ("concierge", USER_MESSAGE),
    ]


def test_fallback_when_entry_blank_or_short():
    tasks = _tasks_for(
        SupervisorIntent(
            target_agent="planner",
            plan=["concierge"],
            task_queries=["find flights", " "],
        )
    )
    assert _queries(tasks) == [
        ("planner", "find flights"),
        ("concierge", USER_MESSAGE),
    ]
    short = _tasks_for(
        SupervisorIntent(
            target_agent="planner",
            plan=["concierge"],
            task_queries=["find flights", "ok"],
        )
    )
    assert _queries(short)[1] == ("concierge", USER_MESSAGE)


def test_alignment_survives_plan_dedup():
    # plan repeats the primary: the dedup loop drops the second planner, but the
    # queries are aligned to the pre-dedup [target, *plan] positions, so the
    # concierge still receives the third entry.
    tasks = _tasks_for(
        SupervisorIntent(
            target_agent="planner",
            plan=["planner", "concierge"],
            task_queries=["query a", "query b", "query c"],
        )
    )
    assert _queries(tasks) == [
        ("planner", "query a"),
        ("concierge", "query c"),
    ]


def test_length_mismatch_falls_back_for_all():
    tasks = _tasks_for(
        SupervisorIntent(
            target_agent="planner",
            plan=["concierge"],
            task_queries=["only one"],
        )
    )
    assert _queries(tasks) == [
        ("planner", USER_MESSAGE),
        ("concierge", USER_MESSAGE),
    ]


def test_task_queries_defaults_to_none():
    assert SupervisorIntent(target_agent="planner").task_queries is None


# --- malformed task_queries degrade instead of raising (function_calling is not
# strict-schema, so the model can emit any JSON). Built through model_validate:
# FakeLLM returns instances verbatim and would bypass the validator.


def _validated(task_queries: object) -> SupervisorIntent:
    return SupervisorIntent.model_validate(
        {"target_agent": "planner", "plan": ["concierge"], "task_queries": task_queries}
    )


def test_task_queries_non_string_entry_is_blanked():
    assert _validated(["find flights", None]).task_queries == ["find flights", ""]


def test_task_queries_bare_string_is_wrapped():
    assert _validated("find flights").task_queries == ["find flights"]


def test_task_queries_non_list_is_dropped():
    assert _validated({"q": "x"}).task_queries is None


def test_task_queries_unhashable_entry_does_not_raise():
    assert _validated([["nested"], {"a": 1}]).task_queries == ["", ""]


def test_malformed_entry_falls_back_through_supervisor():
    tasks = _tasks_for(_validated(["find flights", None]))
    assert _queries(tasks) == [
        ("planner", "find flights"),
        ("concierge", USER_MESSAGE),
    ]


def test_task_queries_wire_schema_stays_string_array():
    prop = SupervisorIntent.model_json_schema()["properties"]["task_queries"]
    assert {"type": "array", "items": {"type": "string"}} in prop["anyOf"]
    assert {"type": "null"} in prop["anyOf"]
