"""Rubric grader node tests (specs/min-59-runtime-self-eval-loop).

Verifies the grader node's routing contract:
- delegates to "reflection" when disabled or the flow has no rubric (baseline A/B);
- ends the turn on a satisfied verdict (answer accepted as-is);
- loops back to the sub-agent with SystemMessage feedback on needs_revision;
- fail-open (END, answer kept) on max_iterations and on grader errors.

All tests are offline: FakeLLM.structured_responses feeds the verdicts.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.agents.context import AgentContext
from app.agents.grader import CriterionResult, GraderResponse, make_grader_node
from app.clients.llm import FakeLLM
from app.enums import GraderVerdict
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END
from pydantic import ValidationError


def _runtime(ctx: AgentContext | None = None):
    """Minimal runtime stand-in: exposes only .context, which is all nodes read."""
    return SimpleNamespace(context=ctx)


def _state(**overrides):
    state = {
        "messages": [
            HumanMessage(content="tìm khách sạn ở Đà Nẵng"),
            AIMessage(content="Here are 3 hotels..."),
        ],
        "revisions": 0,
        "grader_iterations": 0,
        "grader_verdict": None,
        "current_flow": "concierge",
        "user_id": None,
        "trip_id": None,
        "summary": None,
        "trip_context": None,
    }
    state.update(overrides)
    return state


def _satisfied():
    return GraderResponse(evaluations=[CriterionResult(name="grounding", passed=True)])


def _needs_revision():
    return GraderResponse(
        evaluations=[
            CriterionResult(name="grounding", passed=True),
            CriterionResult(
                name="language",
                passed=False,
                gap="Reply in Vietnamese — the traveller wrote in Vietnamese.",
            ),
        ]
    )


def test_grader_delegates_to_reflection_when_disabled():
    """allow_grader=False routes to the reflection node — the exact baseline path."""
    llm = FakeLLM(structured_responses=[_satisfied()])  # must NOT be consumed
    grade = make_grader_node(llm)

    result = grade(_state(), _runtime(AgentContext(allow_grader=False)))

    assert result.goto == "reflection"
    assert llm._structured_cursor == 0


def test_grader_delegates_for_ungraded_flow():
    """A flow without a rubric (planner) falls through to reflection untouched."""
    llm = FakeLLM(structured_responses=[_satisfied()])
    grade = make_grader_node(llm)

    result = grade(_state(current_flow="planner"), _runtime(AgentContext()))

    assert result.goto == "reflection"
    assert llm._structured_cursor == 0


def test_grader_satisfied_ends_turn():
    """All criteria passed -> the answer ships as-is."""
    llm = FakeLLM(structured_responses=[_satisfied()])
    grade = make_grader_node(llm)

    result = grade(_state(), _runtime(AgentContext()))

    assert result.goto == END
    assert result.update["grader_verdict"] == GraderVerdict.SATISFIED


def test_grader_needs_revision_loops_with_system_feedback():
    """A failed criterion loops back to the sub-agent with SystemMessage feedback."""
    llm = FakeLLM(structured_responses=[_needs_revision()])
    grade = make_grader_node(llm)

    result = grade(_state(), _runtime(AgentContext()))

    assert result.goto == "concierge"
    assert result.update["grader_iterations"] == 1
    assert result.update["grader_verdict"] == GraderVerdict.NEEDS_REVISION
    (feedback,) = result.update["messages"]
    assert isinstance(feedback, SystemMessage)  # NEVER HumanMessage (language-flip bug)
    assert "language" in feedback.content
    assert "Reply in Vietnamese" in feedback.content
    assert "internal review note" in feedback.content


def test_grader_never_touches_reflections_revisions_counter():
    """The grader must not write ``revisions`` — that counter belongs to reflection.

    Sharing it let a grader revision on booking/concierge exhaust reflection's cap,
    silently disabling reflection for every later turn of the conversation
    (ESCALATIONS.md E1).
    """
    llm = FakeLLM(structured_responses=[_needs_revision()])
    grade = make_grader_node(llm)

    result = grade(_state(revisions=0), _runtime(AgentContext()))

    assert "revisions" not in result.update


def test_grader_grades_the_final_draft_before_stopping():
    """At the cap the judge still runs, so the shipped answer was actually graded.

    Checking the cap first would return the last revision unevaluated while logging
    ``max_iterations_reached`` — which reads like a quality verdict but means
    "never looked at".
    """
    llm = FakeLLM(structured_responses=[_needs_revision()])
    grade = make_grader_node(llm, max_iterations=2)

    result = grade(_state(grader_iterations=2), _runtime(AgentContext()))

    assert result.goto == END
    assert result.update["grader_verdict"] == GraderVerdict.MAX_ITERATIONS_REACHED
    assert llm._structured_cursor == 1  # the final draft WAS graded


def test_grader_satisfied_at_the_cap_still_ends_satisfied():
    """A final revision that fixes everything is reported as satisfied, not as a cap hit."""
    llm = FakeLLM(structured_responses=[_satisfied()])
    grade = make_grader_node(llm, max_iterations=2)

    result = grade(_state(grader_iterations=2), _runtime(AgentContext()))

    assert result.goto == END
    assert result.update["grader_verdict"] == GraderVerdict.SATISFIED


def test_grader_error_fails_open():
    """A grader exception keeps the original answer (END), never blocks the reply."""
    llm = FakeLLM(structured_responses=[])  # with_structured_output raises ValueError
    grade = make_grader_node(llm)

    result = grade(_state(), _runtime(AgentContext()))

    assert result.goto == END
    assert result.update["grader_verdict"] == GraderVerdict.GRADER_ERROR


def test_grader_reraises_transient_llm_errors_for_retry_policy():
    """A retryable provider error must propagate so the node's LLM_RETRY can fire.

    Swallowing it here would make ``retry_policy=LLM_RETRY`` on the grader node
    dead code, skipping the rubric on a single network blip.
    """

    class _Transient(Exception):
        status_code = 503

    class _BoomLLM(FakeLLM):
        def with_structured_output(self, schema, **kwargs):
            def _raise(_messages):
                raise _Transient("upstream down")

            return RunnableLambda(_raise)

    grade = make_grader_node(_BoomLLM())

    with pytest.raises(_Transient):
        grade(_state(), _runtime(AgentContext()))


def test_grader_empty_evaluations_is_an_error_not_an_approval():
    """A judge that returns no criteria must not be read as 'nothing failed'."""
    with pytest.raises(ValidationError):
        GraderResponse(evaluations=[])


def test_grader_default_context_none_is_enabled():
    """No runtime context behaves like defaults (grader on) — parity with reflection."""
    llm = FakeLLM(structured_responses=[_satisfied()])
    grade = make_grader_node(llm)

    result = grade(_state(), _runtime(None))

    assert result.goto == END


# ---------------------------------------------------------------------------
# Graph wiring — booking/concierge route through grader; others unchanged
# ---------------------------------------------------------------------------


def _compiled_edges():
    from app.agents.graph import build_graph

    fake = FakeLLM(responses=["OK"])
    compiled = build_graph(llm=fake, fast_llm=fake)
    return {(e.source, e.target) for e in compiled.get_graph().edges}


def test_graded_flows_route_through_grader():
    edges = _compiled_edges()
    assert ("booking", "grader") in edges
    assert ("concierge", "grader") in edges
    assert ("booking", "reflection") not in edges
    assert ("concierge", "reflection") not in edges


def test_ungraded_flows_keep_reflection_edge():
    edges = _compiled_edges()
    for name in ("planner", "journal", "budget"):
        assert (name, "reflection") in edges


def test_grader_budget_does_not_leak_into_the_next_turn():
    """A grader revision on turn 1 must not disable reflection on turn 2.

    Regression for ESCALATIONS.md E1: the grader used to increment reflection's
    ``revisions`` counter, which is checkpointed and never reset, so one revision on
    concierge silently short-circuited reflection for every later turn of the thread.
    ``load_context_node`` now resets the grader's turn-scoped budget.
    """
    from app.agents.nodes import load_context_node

    # End of turn 1: the grader used its full budget on a graded flow.
    end_of_turn_1 = {"grader_iterations": 2, "revisions": 0}

    # Turn 2 starts by re-entering load_context.
    reset = load_context_node({"messages": [], "trip_id": None}, SimpleNamespace())

    assert reset["grader_iterations"] == 0
    # ...and reflection's own counter was never touched by the grader at all.
    assert end_of_turn_1["revisions"] == 0
