"""The reflection judge must never be called with a conversation ending on an assistant turn.

Claude rejects that shape with a 400 ("does not support assistant message prefill"),
which failed every non-trivial turn on ``LLM_PROVIDER=anthropic`` (T8 keyed smoke).
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.nodes import make_reflection_node
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END


class _Spy(GenericFakeChatModel):
    seen: list = []

    def _generate(self, messages, *a, **k):
        self.seen.append(list(messages))
        return super()._generate(messages, *a, **k)


def test_judge_gets_the_answer_as_a_user_turn():
    llm = _Spy(messages=iter([AIMessage(content="OK")]), seen=[])
    node = make_reflection_node(llm)
    state = {
        "messages": [
            HumanMessage(content="weather in Tokyo?"),
            AIMessage(content=[{"type": "text", "text": "Sunny, 24C."}]),
        ],
        "revisions": 0,
        "current_flow": "concierge",
    }
    cmd = node(state, SimpleNamespace(context=None))

    assert cmd.goto == END
    sent = llm.seen[0]
    assert isinstance(sent[-1], HumanMessage)
    assert "Sunny, 24C." in sent[-1].content


def test_midstream_system_messages_are_demoted_for_the_model_call():
    """Claude rejects non-leading system messages ("multiple non-consecutive system messages")."""
    from app.agents.state import demote_midstream_system
    from langchain_core.messages import SystemMessage

    history = [
        HumanMessage(content="hi"),
        AIMessage(content="draft"),
        SystemMessage(content="revise please"),
    ]
    out = demote_midstream_system(history)
    assert [type(m) for m in out] == [HumanMessage, AIMessage, HumanMessage]
    assert "revise please" in out[-1].content
    assert isinstance(history[-1], SystemMessage)  # state is not mutated
