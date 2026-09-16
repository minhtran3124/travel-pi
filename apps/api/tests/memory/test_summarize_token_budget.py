"""Token-aware compression trigger (specs/agent-memory-layer-5 Task 1.2).

Covers the OR branch added to ``should_summarize``: compression fires on
estimated token pressure (``chars / 4``, counting tool-call arguments) even when
the message count is below the count threshold, while the original count branch
stays reachable. See ``design.md`` §4.2 and the plan's Global Constraints.
"""

from __future__ import annotations

from app.memory.summarizer import should_summarize
from langchain_core.messages import AIMessage, HumanMessage


def test_short_but_token_heavy_history_triggers():
    """A few messages carrying large payloads trip the token branch."""
    # 3 messages — well below any sane count threshold — but each content is huge.
    big = "word " * 4000  # ~20k chars ⇒ ~5k tokens each, ~15k total
    msgs = [
        HumanMessage(content=big),
        AIMessage(content=big),
        HumanMessage(content=big),
    ]
    # Count threshold high enough to prove the count branch did NOT fire.
    assert should_summarize(msgs, threshold=50, token_budget=12000) is True


def test_token_payload_in_tool_calls_is_counted():
    """Tokens hidden in ``tool_calls`` args (not ``content``) still count."""
    heavy_args = {"payload": "x" * 60000}  # ~60k chars ⇒ ~15k tokens
    msg = AIMessage(
        content="",  # empty content — all weight is in the tool call
        tool_calls=[
            {"name": "search", "args": heavy_args, "id": "call_1", "type": "tool_call"}
        ],
    )
    assert should_summarize([msg], threshold=50, token_budget=12000) is True


def test_long_but_light_history_triggers_via_count():
    """A long thread of tiny messages still trips the original count branch."""
    msgs = [HumanMessage(content="x") for _ in range(30)]
    # Token budget huge so the token branch cannot fire; only the count can.
    assert should_summarize(msgs, threshold=20, token_budget=10_000_000) is True


def test_small_light_history_triggers_neither():
    """A short, light thread compresses on neither branch."""
    msgs = [HumanMessage(content="hi"), AIMessage(content="hello")]
    assert should_summarize(msgs, threshold=20, token_budget=12000) is False


def test_multimodal_list_content_does_not_raise():
    """List/dict content (multimodal blocks) is tolerated, not crashed on."""
    msgs = [
        HumanMessage(
            content=[
                {"type": "text", "text": "short"},
                {"type": "image_url", "image_url": {"url": "data:..."}},
            ]
        )
    ]
    # Should simply return a bool without raising.
    assert should_summarize(msgs, threshold=20, token_budget=12000) is False
