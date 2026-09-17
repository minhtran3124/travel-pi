"""Specialist sub-agents."""

import pytest
from langchain_core.messages import HumanMessage


@pytest.mark.parametrize(
    "builder_name",
    [
        "build_planner",
        "build_concierge",
        "build_journal",
        "build_booking",
        "build_budget",
    ],
)
def test_subagents_build_and_answer(builder_name):
    """Each sub-agent compiles and answers directly when the LLM emits no tool call."""
    import importlib

    from app.clients.llm import FakeLLM

    domain = builder_name.removeprefix("build_")
    mod = importlib.import_module(f"app.agents.subagents.{domain}")
    builder = getattr(mod, builder_name)

    fake = FakeLLM(responses=["here is my answer"])
    agent = builder(lambda _: fake)
    out = agent.invoke({"messages": [HumanMessage(content="hi")]})
    assert out["messages"][-1].content == "here is my answer"


def test_concierge_has_knowledge_tool():
    from app.tools.registry import get_tools_for

    names = {t.name for t in get_tools_for("concierge")}
    assert "search_travel_knowledge" in names
