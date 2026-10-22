"""Hotel-search intent routing tests.

FakeLLM injects supervisor intent, so these validate structural wiring (routing
target, tool binding, artifact shape) — not the model's own tool choice, which
only the eval can prove.
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


def test_concierge_can_call_search_hotels_with_dates(agent_db):
    from app.agents.subagents._base import build_subagent
    from app.prompts.registry import registry
    from app.tools.registry import get_tools_for

    fake = FakeLLM(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_hotels",
                        "args": {
                            "city": "Da Nang",
                            "check_in": "2027-03-10",
                            "check_out": "2027-03-13",
                            "rooms": 1,
                            "adults": 2,
                            "children": 1,
                        },
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
        {
            "messages": [
                HumanMessage(
                    content="find me a hotel in Da Nang from 2027-03-10 to 2027-03-13"
                )
            ]
        }
    )

    tool_msgs = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert tool_msgs, "expected search_hotels to be called"
    search_result = next(m for m in tool_msgs if m.name == "search_hotels")
    assert search_result.artifact["kind"] == "hotels"
    assert search_result.artifact["data"]["nights"] > 0

    assert "book_hotel" not in {t.name for t in get_tools_for("concierge")}


def test_concierge_dated_hotel_turn_does_not_interrupt():
    graph = _build(intent_target="concierge", answer="Here are some hotels in Da Nang.")
    result = _invoke(
        graph,
        "find me a hotel in Da Nang from 2027-03-10 to 2027-03-13",
        thread_id="t-hotel-search-dated-1",
    )

    assert not result.get("__interrupt__"), (
        "a dated hotel search must complete without a plan-approval interrupt"
    )
    assert result["current_flow"] == "concierge"
