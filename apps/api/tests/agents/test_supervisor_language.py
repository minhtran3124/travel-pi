from app.agents.supervisor import SupervisorIntent, make_supervisor
from langchain_core.messages import HumanMessage


class _RouterLLM:
    """Fake structured-output LLM returning a scripted SupervisorIntent."""

    def __init__(self, intent):
        self._intent = intent

    def with_structured_output(self, *_a, **_k):
        return self

    def invoke(self, _messages):
        return self._intent


def test_supervisor_persists_language():
    llm = _RouterLLM(SupervisorIntent(target_agent="concierge", language="vi"))
    node = make_supervisor(llm)
    cmd = node(
        {"messages": [HumanMessage("Thời tiết Đà Nẵng?")], "language": "en"}, None
    )
    assert cmd.update["language"] == "vi"


def test_supervisor_falls_back_to_state_when_code_empty():
    llm = _RouterLLM(SupervisorIntent(target_agent="concierge", language=""))
    node = make_supervisor(llm)
    cmd = node({"messages": [HumanMessage("ok")], "language": "vi"}, None)
    assert cmd.update["language"] == "vi"
