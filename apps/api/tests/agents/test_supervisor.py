"""Supervisor + cross-cutting nodes (specs/travel-agent Task 5.3)."""

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END


def test_supervisor_routes_to_target():
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="planner")])
    supervisor = make_supervisor(llm)
    cmd = supervisor({"messages": [HumanMessage(content="plan my trip")]})
    assert cmd.goto == "planner"
    assert cmd.update["current_flow"] == "planner"


def test_supervisor_unknown_intent_ends():
    from app.agents.supervisor import make_supervisor
    from app.clients.llm import FakeLLM

    # structured output returns an object whose target_agent isn't a known agent
    class Weird:
        target_agent = "spaceship"

    llm = FakeLLM(structured_responses=[Weird()])
    supervisor = make_supervisor(llm)
    cmd = supervisor({"messages": [HumanMessage(content="???")]})
    assert cmd.goto == END


def test_summarize_node_compresses_when_long():
    from app.agents.nodes import make_summarize_node
    from app.clients.llm import FakeLLM

    msgs = [HumanMessage(content=f"m{i}", id=f"m{i}") for i in range(25)]
    node = make_summarize_node(FakeLLM(responses=["SUMMARY"]))
    out = node({"messages": msgs})
    assert out["summary"] == "SUMMARY"
    assert len(out["messages"]) > 0  # RemoveMessage entries


def test_summarize_node_noop_when_short():
    from app.agents.nodes import make_summarize_node
    from app.clients.llm import FakeLLM

    node = make_summarize_node(FakeLLM(responses=["x"]))
    assert node({"messages": [HumanMessage(content="hi")]}) == {}


def test_reflection_ok_ends():
    from app.agents.nodes import make_reflection_node
    from app.clients.llm import FakeLLM

    node = make_reflection_node(FakeLLM(responses=["OK"]))
    cmd = node(
        {"messages": [AIMessage(content="great answer")], "current_flow": "planner"}
    )
    assert cmd.goto == END


def test_reflection_revise_loops_back_then_stops():
    from app.agents.nodes import make_reflection_node
    from app.clients.llm import FakeLLM

    node = make_reflection_node(FakeLLM(responses=["REVISE"]))
    # first pass: revisions 0 -> loops back to the active sub-agent
    cmd = node({"messages": [AIMessage(content="bad")], "current_flow": "planner"})
    assert cmd.goto == "planner"
    assert cmd.update["revisions"] == 1
    # second pass: already at max -> ends regardless of verdict
    cmd2 = node(
        {
            "messages": [AIMessage(content="bad")],
            "current_flow": "planner",
            "revisions": 1,
        }
    )
    assert cmd2.goto == END
