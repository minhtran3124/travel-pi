"""Concierge exclude_names wiring end-to-end (MIN-50 reproduction test)."""

from langchain_core.messages import AIMessage, HumanMessage
from tests.tools.conftest import (
    agent_db,  # noqa: F401 — fixture not visible cross-package
)


def test_concierge_exclude_names_omits_prior_suggestions(agent_db):
    from app.agents.subagents._base import build_subagent
    from app.clients.llm import FakeLLM
    from app.prompts.registry import registry
    from app.tools.registry import get_tools_for

    fake = FakeLLM(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_places",
                        "args": {
                            "city": "Tokyo",
                            "exclude_names": ["Senso-ji Temple", "Shibuya Crossing"],
                        },
                        "id": "c1",
                    }
                ],
            ),
            "Here are a couple more spots in Tokyo.",
        ]
    )
    subgraph = build_subagent(
        "test_concierge_dedup",
        get_tools_for("concierge"),
        lambda _: fake,
        registry.get("concierge"),
    )

    result = subgraph.invoke(
        {"messages": [HumanMessage(content="any other places in Tokyo?")]}
    )

    tool_msgs = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert tool_msgs, "expected search_places to be called"
    content = str(tool_msgs[-1].content)
    assert "Senso-ji Temple" not in content
    assert "Shibuya Crossing" not in content
