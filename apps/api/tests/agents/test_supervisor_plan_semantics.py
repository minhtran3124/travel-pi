"""Supervisor `plan` semantics.

The runtime is parallel-only: tasks are built from a deduplicated agent list
(primary first, then each plan follow-on, skipping already-queued agents), the
gates (unknown intent, booking never a follow-on, tier gating, MAX_LEDGER_STEPS)
still hold, and pending_flows is no longer written.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from types import SimpleNamespace

from app.agents.constants import MAX_LEDGER_STEPS
from app.agents.context import AgentContext, resolve_agent_context
from app.agents.supervisor import SupervisorIntent, make_supervisor
from app.clients.llm import FakeLLM
from langchain_core.messages import HumanMessage


def _runtime(ctx: AgentContext) -> SimpleNamespace:
    return SimpleNamespace(context=ctx)


def _agents_for(intent: SupervisorIntent, ctx: AgentContext) -> list[str]:
    supervisor = make_supervisor(FakeLLM(structured_responses=[intent]))
    cmd = supervisor({"messages": [HumanMessage(content="x")]}, _runtime(ctx))
    assert "pending_flows" not in cmd.update
    return [t["agent"] for t in cmd.update.get("tasks", [])]


def test_plan_repeating_primary_is_deduped():
    # A second planner worker would only redo the primary's work, so it is dropped.
    agents = _agents_for(
        SupervisorIntent(target_agent="planner", plan=["concierge", "planner"]),
        AgentContext(),
    )
    assert agents == ["planner", "concierge"]


def test_plan_equal_to_primary_yields_single_task():
    agents = _agents_for(
        SupervisorIntent(target_agent="planner", plan=["planner"]),
        AgentContext(),
    )
    assert agents == ["planner"]


def test_plan_repeated_follow_on_is_deduped():
    agents = _agents_for(
        SupervisorIntent(target_agent="planner", plan=["concierge", "concierge"]),
        AgentContext(),
    )
    assert agents == ["planner", "concierge"]


def test_independent_secondary_is_kept():
    agents = _agents_for(
        SupervisorIntent(target_agent="planner", plan=["concierge"]),
        AgentContext(),
    )
    assert agents == ["planner", "concierge"]


def test_legacy_secondary_agent_is_ignored():
    intent = SupervisorIntent.model_validate(
        {"target_agent": "planner", "secondary_agent": "budget"}
    )
    agents = _agents_for(intent, AgentContext())
    assert agents == ["planner"]


def test_supervisor_intent_has_no_secondary_agent_field():
    assert "secondary_agent" not in SupervisorIntent.model_fields


def test_raw_payload_with_secondary_booking_does_not_raise():
    intent = SupervisorIntent.model_validate(
        {"target_agent": "planner", "secondary_agent": "booking"}
    )
    assert intent.plan is None


def test_nested_object_is_coerced():
    intent = SupervisorIntent.model_validate(
        {
            "target_agent": "planner",
            "plan": [{"target_agent": "journal", "slots": None}],
        }
    )
    assert intent.plan == ["journal"]


def test_booking_in_plan_is_dropped():
    # booking is dropped as a follow-on, not rejected.
    intent = SupervisorIntent.model_validate(
        {"target_agent": "planner", "plan": ["booking", "concierge"]}
    )
    assert intent.plan == ["concierge"]


def test_unparseable_entries_are_dropped():
    # Nothing survives, so plan becomes None.
    intent = SupervisorIntent.model_validate(
        {
            "target_agent": "planner",
            "plan": ["nope", 7, {"x": 1}, {"target_agent": "booking"}],
        }
    )
    assert intent.plan is None


def test_wire_schema_keeps_plan_enum():
    # The tolerant before-validator must not change the JSON schema sent to the model.
    plan_schema = SupervisorIntent.model_json_schema()["properties"]["plan"]
    array_branches = [b for b in plan_schema["anyOf"] if b.get("type") == "array"]
    assert len(array_branches) == 1
    assert array_branches[0]["items"]["enum"] == [
        "planner",
        "concierge",
        "journal",
        "budget",
    ]


def test_coerced_plan_reaches_tasks():
    intent = SupervisorIntent.model_validate(
        {
            "target_agent": "planner",
            "plan": [{"target_agent": "journal", "slots": None}],
        }
    )
    agents = _agents_for(intent, AgentContext())
    assert agents == ["planner", "journal"]


def test_dropped_entry_is_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="app.agents.supervisor"):
        SupervisorIntent.model_validate(
            {"target_agent": "planner", "plan": ["booking"]}
        )
    assert "booking" in caplog.text


def test_command_update_omits_pending_flows():
    supervisor = make_supervisor(
        FakeLLM(
            structured_responses=[
                SupervisorIntent(target_agent="planner", plan=["concierge"])
            ]
        )
    )
    cmd = supervisor(
        {"messages": [HumanMessage(content="flights and food")]},
        _runtime(AgentContext()),
    )
    assert "pending_flows" not in cmd.update
    assert set(cmd.update) == {"current_flow", "language", "trip_facts", "tasks"}


def test_booking_target_has_no_followons():
    # booking routes to HITL alone; follow-ons are dropped.
    agents = _agents_for(
        SupervisorIntent(target_agent="booking", plan=["concierge", "budget"]),
        AgentContext(),
    )
    assert agents == ["booking"]


def test_tier_gated_follow_on_is_dropped():
    narrow = replace(
        resolve_agent_context(tier="free"),
        allowed_subagents=frozenset({"concierge"}),
    )
    agents = _agents_for(
        SupervisorIntent(target_agent="concierge", plan=["planner", "budget"]),
        narrow,
    )
    assert agents == ["concierge"]


def test_tier_gated_primary_emits_no_tasks():
    supervisor = make_supervisor(
        FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")])
    )
    cmd = supervisor(
        {"messages": [HumanMessage(content="book me a hotel")]},
        _runtime(resolve_agent_context(tier="free")),
    )
    assert "tasks" not in cmd.update
    assert "pending_flows" not in cmd.update


def test_follow_ons_capped_at_max_ledger_steps():
    # Follow-ons are truncated so primary + cap = MAX_LEDGER_STEPS total.
    over_long = ["concierge", "budget", "journal", "concierge", "budget"]
    agents = _agents_for(
        SupervisorIntent(target_agent="planner", plan=over_long),
        AgentContext(),
    )
    assert agents == ["planner", "concierge", "budget", "journal"]
    assert len(agents) == MAX_LEDGER_STEPS


def test_unhashable_nested_target_agent_does_not_raise():
    # An unhashable nested target_agent once raised TypeError from a `value in <set>`
    # test — the same dead turn the validator exists to prevent.
    for bad in ([{"target_agent": ["planner"]}], [{"target_agent": {"a": 1}}]):
        intent = SupervisorIntent.model_validate(
            {"target_agent": "planner", "plan": bad}
        )
        assert intent.plan is None
