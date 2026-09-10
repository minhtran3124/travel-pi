"""Supervisor `plan` semantics — wave 1 (specs/multi-intent-single-path).

The runtime is parallel-only: every task in ``tasks`` is dispatched to a blind
``synthesis_worker`` that sees only this message. The supervisor therefore:

- builds ``tasks`` from a DEDUPLICATED agent list — primary first, then each
  ``plan`` follow-on in order, skipping any agent already queued (no duplicate
  specialist workers) and never the primary itself;
- keeps the existing gates (unknown intent, ``booking`` never queued as a
  follow-on, tier-gated agents dropped) and the ``MAX_LEDGER_STEPS`` cap;
- no longer writes ``pending_flows`` (the dead sequential ledger; wave 2 removes
  the state field).

Direct supervisor calls with a FakeLLM structured response (the pattern in
``test_task_ledger.py``).
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
    # Wave 1: the supervisor never writes the sequential ledger anymore.
    assert "pending_flows" not in cmd.update
    return [t["agent"] for t in cmd.update.get("tasks", [])]


# ---------------------------------------------------------------------------
# Dedupe: a follow-on that repeats the primary (or an earlier step) is dropped
# ---------------------------------------------------------------------------


def test_plan_repeating_primary_is_deduped():
    # plan=[concierge, planner] with target=planner → [planner, concierge].
    # A parallel worker sees only this message, so a second planner worker would
    # only redo the same work — it is dropped.
    agents = _agents_for(
        SupervisorIntent(target_agent="planner", plan=["concierge", "planner"]),
        AgentContext(),
    )
    assert agents == ["planner", "concierge"]


def test_plan_equal_to_primary_yields_single_task():
    # plan=[planner] (== primary) collapses to exactly one planner task.
    agents = _agents_for(
        SupervisorIntent(target_agent="planner", plan=["planner"]),
        AgentContext(),
    )
    assert agents == ["planner"]


def test_plan_repeated_follow_on_is_deduped():
    # A follow-on repeated within the plan is queued once.
    agents = _agents_for(
        SupervisorIntent(target_agent="planner", plan=["concierge", "concierge"]),
        AgentContext(),
    )
    assert agents == ["planner", "concierge"]


# ---------------------------------------------------------------------------
# Independent secondary is kept
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Invalid plan entries degrade instead of raising
# ---------------------------------------------------------------------------


def test_nested_object_is_coerced():
    # A nested {"target_agent": ...} step is unwrapped to the bare name.
    intent = SupervisorIntent.model_validate(
        {
            "target_agent": "planner",
            "plan": [{"target_agent": "journal", "slots": None}],
        }
    )
    assert intent.plan == ["journal"]


def test_booking_in_plan_is_dropped():
    # 'booking' can never be queued as a follow-on; it is dropped, not rejected.
    intent = SupervisorIntent.model_validate(
        {"target_agent": "planner", "plan": ["booking", "concierge"]}
    )
    assert intent.plan == ["concierge"]


def test_unparseable_entries_are_dropped():
    # Unknown string, int, dict without a valid target_agent, nested booking:
    # all dropped; nothing survives so plan becomes None.
    intent = SupervisorIntent.model_validate(
        {
            "target_agent": "planner",
            "plan": ["nope", 7, {"x": 1}, {"target_agent": "booking"}],
        }
    )
    assert intent.plan is None


def test_wire_schema_keeps_plan_enum():
    # The tolerant before-validator must not change the JSON schema sent to the
    # model (SC-4): the array branch still lists the four-name enum.
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
    # End to end: a raw nested journal entry yields tasks [planner, journal].
    intent = SupervisorIntent.model_validate(
        {
            "target_agent": "planner",
            "plan": [{"target_agent": "journal", "slots": None}],
        }
    )
    agents = _agents_for(intent, AgentContext())
    assert agents == ["planner", "journal"]


def test_dropped_entry_is_logged(caplog):
    # Every dropped entry is logged at WARNING with the rejected value.
    with caplog.at_level(logging.WARNING, logger="app.agents.supervisor"):
        SupervisorIntent.model_validate(
            {"target_agent": "planner", "plan": ["booking"]}
        )
    assert "booking" in caplog.text


# ---------------------------------------------------------------------------
# The supervisor no longer writes pending_flows
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Existing gates still hold: booking exclusion + tier gating
# ---------------------------------------------------------------------------


def test_booking_target_has_no_followons():
    # booking routes to HITL alone; any plan follow-ons are dropped.
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
    # A free user routed to booking degrades to an upgrade message, no tasks.
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
    # More distinct independent follow-ons than the cap are truncated to
    # MAX_LEDGER_STEPS - 1 (primary + cap = MAX_LEDGER_STEPS tasks total).
    over_long = ["concierge", "budget", "journal", "concierge", "budget"]
    agents = _agents_for(
        SupervisorIntent(target_agent="planner", plan=over_long),
        AgentContext(),
    )
    assert agents == ["planner", "concierge", "budget", "journal"]
    assert len(agents) == MAX_LEDGER_STEPS


def test_unhashable_nested_target_agent_does_not_raise():
    # GH-180 regression: the validator unwraps a nested object by reading
    # ``target_agent``, whose value is whatever the model emitted. A list or dict
    # there is unhashable, so an unguarded ``value in <set>`` membership test
    # raised TypeError straight out of the supervisor node — the same dead turn
    # the validator exists to prevent, just with a different exception class.
    for bad in ([{"target_agent": ["planner"]}], [{"target_agent": {"a": 1}}]):
        intent = SupervisorIntent.model_validate(
            {"target_agent": "planner", "plan": bad}
        )
        assert intent.plan is None
