"""Unit test for the synthesize node's outgoing system message (specs/gh-146 Task 1.1)."""

from langchain_core.messages import HumanMessage, SystemMessage


def test_synthesize_system_message_includes_language_directive():
    from app.agents.nodes import make_synthesize_node
    from app.clients.llm import FakeLLM

    captured: dict = {}

    class CapturingLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    capturing = CapturingLLM(responses=["ok"])
    node = make_synthesize_node(capturing)
    result = node(
        {
            "task_results": [{"agent": "budget", "findings": "x", "index": 0}],
            "language": "en",
            "messages": [],
        }
    )

    system_msg = captured["messages"][0]
    human_msg = captured["messages"][1]
    assert isinstance(system_msg, SystemMessage)
    assert "Reply in the traveller's own language: en" in system_msg.content
    assert "Combine the specialist findings" in system_msg.content
    assert isinstance(human_msg, HumanMessage)
    assert "Conversation language: en" in human_msg.content
    assert result["current_flow"] == "synthesize"


def test_synthesize_system_message_unchanged_without_language():
    from app.agents.nodes import make_synthesize_node
    from app.clients.llm import FakeLLM

    captured: dict = {}

    class CapturingLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    capturing = CapturingLLM(responses=["ok"])
    node = make_synthesize_node(capturing)
    result = node(
        {
            "task_results": [{"agent": "budget", "findings": "x", "index": 0}],
            "messages": [],
        }
    )

    system_msg = captured["messages"][0]
    assert "Reply in the traveller's own language" not in system_msg.content
    assert result["current_flow"] == "synthesize"
