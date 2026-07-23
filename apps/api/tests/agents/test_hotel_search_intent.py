"""Hotel-search intent routing tests (specs/min-51-hotel-search-intent Task 3.2).

Verifies that:
- A hotel-search-style message routed to the concierge sub-agent completes
  without a plan-approval interrupt (only booking triggers HITL).
- A booking-intent message still interrupts as before (regression guard).
- The concierge sub-agent can actually call ``browse_hotels`` (the dateless
  catalog browse) and get back a ``kind="hotels"`` panel artifact.

FakeLLM-driven graph tests bypass prompt CONTENT for routing (supervisor
intent is injected via ``structured_responses``), so (a)/(b) validate the
STRUCTURAL wiring (routing target -> interrupt-or-not), not the LLM's
prompt-following. (c) validates that concierge's tool binding actually
includes ``browse_hotels`` and that invoking it produces the expected
ToolMessage + artifact shape.
"""

from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from tests.tools.conftest import (
    agent_db,  # noqa: F401 — fixture not visible cross-package
)


def _build(intent_target: str, answer: str = "done", verdict: str = "OK"):
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=intent_target)] * 6,
        responses=[answer] * 6,
    )
    fast = FakeLLM(responses=[verdict] * 6)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, thread_id: str, **extra):
    return graph.invoke(
        {
            "messages": [HumanMessage(content=msg)],
            "user_id": "u1",
            "trip_id": None,
            **extra,
        },
        {"configurable": {"thread_id": thread_id}},
    )


def test_hotel_search_routes_to_concierge_without_interrupt():
    graph = _build(intent_target="concierge", answer="Here are some hotels in Da Nang.")
    result = _invoke(
        graph,
        "find me a hotel in Da Nang for next weekend",
        thread_id="t-hotel-search-1",
    )

    assert not result.get("__interrupt__"), (
        "hotel search must complete without a plan-approval interrupt"
    )
    assert result["current_flow"] == "concierge"


def test_booking_intent_still_interrupts():
    graph = _build(intent_target="booking", answer="Hotel booked!")
    result = _invoke(graph, "book me a hotel in Da Nang", thread_id="t-hotel-book-1")

    assert result.get("__interrupt__"), "booking must still pause at plan_node"
    payload = result["__interrupt__"][0].value
    assert payload["type"] == "plan_approval"


def test_concierge_can_call_browse_hotels(agent_db):
    from app.agents.subagents._base import build_subagent
    from app.prompts.registry import registry
    from app.tools.registry import get_tools_for

    fake = FakeLLM(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "browse_hotels",
                        "args": {"city": "Da Nang", "max_price": 200},
                        "id": "h1",
                    }
                ],
            ),
            "Here are some hotels — muốn đặt phòng không?",
        ]
    )
    subgraph = build_subagent(
        "concierge_hotel_test",
        get_tools_for("concierge"),
        lambda _: fake,
        registry.get("concierge"),
    )

    result = subgraph.invoke(
        {"messages": [HumanMessage(content="find me a hotel in Da Nang")]}
    )

    tool_msgs = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert tool_msgs, "expected browse_hotels to be called"
    browse_result = next(m for m in tool_msgs if m.name == "browse_hotels")
    assert browse_result.artifact["kind"] == "hotels"
