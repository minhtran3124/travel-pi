"""Summarizer keeps the wrapper tags (specs/rag-tool-output-wrapping Task 1.3, D7 / SC-6).

The summarizer's transcript is the one place tool text becomes *persistent*: the
summary it produces is folded into every later system prompt. So the wrapper tags
added by the tool-output hook are deliberately **kept** in the transcript (no
stripping), and ``_SUMMARY_SYSTEM`` carries a line telling the summarizer that
tagged blocks are retrieved data, not instructions.

``summarize_conversation`` builds the transcript locally and hands it straight to
``llm.invoke``, returning only ``(summary, to_remove)``. Plain ``FakeLLM`` records
nothing it was called with, so there is no way to read the transcript back from it.
``RecordingFakeLLM`` below stashes the ``messages`` it received so the test can
assert on the transcript that actually reached the model — without it this test
would degrade to "a constant contains a string", which proves nothing about D7.
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.tool_output import (
    CLOSE_TAG,
    OPEN_TAG_TEMPLATE,
    TAG_NAME,
    wrap_tool_output,
)
from app.clients.llm import FakeLLM
from app.memory.summarizer import _SUMMARY_SYSTEM, summarize_conversation
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from pydantic import PrivateAttr

_TOOL_NAME = "search_hotels"
_TOOL_PAYLOAD = "Hotel Sofitel Metropole, Hanoi — $210/night, 5 star"

# A wrapped tool block, produced by the real ``wrap_tool_output`` so a tag rename
# in tool_output.py flows through here instead of leaving stale literals behind.
# wrap_tool_output puts a newline right after the opening tag and right before the
# closing tag; that framing is what a stray strip would remove, so keep it.
WRAPPED_TOOL_CONTENT = wrap_tool_output(_TOOL_NAME, _TOOL_PAYLOAD)


class RecordingFakeLLM(FakeLLM):
    """FakeLLM that stashes the messages handed to ``invoke``.

    ``summarize_conversation`` returns only ``(summary, to_remove)``, so the
    transcript is otherwise unobservable. Recording it lets the test assert on
    the exact text that reached the model.
    """

    _recorded: list[BaseMessage] = PrivateAttr(default_factory=list)

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:  # noqa: A002
        self._recorded = list(input)
        return super().invoke(input, config, **kwargs)

    @property
    def recorded(self) -> list[BaseMessage]:
        return self._recorded


def _conversation() -> list[BaseMessage]:
    """A thread whose tool result carries a wrapped <tool_output> block."""
    return [
        HumanMessage(content="Find me a hotel in Hanoi", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[
                {"name": "search_hotels", "args": {"city": "Hanoi"}, "id": "call_1"}
            ],
        ),
        ToolMessage(content=WRAPPED_TOOL_CONTENT, tool_call_id="call_1", id="t1"),
        AIMessage(content="I found the Sofitel Metropole.", id="a2"),
    ]


def test_transcript_keeps_the_wrapper_tags() -> None:
    """The transcript sent to the model still contains the <tool_output> tags.

    D7: the summarizer must NOT strip the wrapper. We read the recorded messages
    to prove the tags are present in the text the model actually received.
    """
    llm = RecordingFakeLLM(responses=["A short running summary."])

    summarize_conversation(_conversation(), llm, keep_last=1)

    assert llm.recorded, "summarize_conversation did not invoke the model"
    transcript = llm.recorded[-1].content
    assert isinstance(transcript, str)

    # The opening and closing tags survive verbatim — nothing stripped them.
    # Derived from the exported constants so a tag rename can't leave this green.
    assert OPEN_TAG_TEMPLATE.format(name=_TOOL_NAME) in transcript
    assert CLOSE_TAG in transcript
    # And the payload inside the block is still there.
    assert _TOOL_PAYLOAD in transcript


def test_summary_system_labels_tagged_blocks_as_data() -> None:
    """_SUMMARY_SYSTEM tells the summarizer not to obey directions inside a tagged block.

    Pin the semantic core, not incidental phrasing. Load-bearing fragments:
    (1) ``TAG_NAME`` — the prompt must name the exact wrapper the hook emits, so a
    rename can't leave the prompt pointing at a tag nobody produces; (2) the safety
    instruction itself — a negated obey-verb ("never/do not follow") plus
    "directions"/"instructions", so the summarizer is told NOT to act on block
    contents. A harmless rephrase of the surrounding sentence keeps these; a gutted
    prompt that drops the don't-obey guarantee fails.
    """
    assert TAG_NAME in _SUMMARY_SYSTEM
    prompt = _SUMMARY_SYSTEM.lower()
    assert re.search(r"(never|not|don't|do not)\s+follow", prompt)
    assert "directions" in prompt or "instructions" in prompt
