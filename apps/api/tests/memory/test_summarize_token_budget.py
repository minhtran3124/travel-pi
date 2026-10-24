"""Token-aware compression trigger (specs/agent-memory-layer-5 Task 1.2).

Covers the OR branch added to ``should_summarize``: compression fires on
estimated token pressure (``chars / 4``, counting tool-call arguments) even when
the message count is below the count threshold, while the original count branch
stays reachable. See ``design.md`` §4.2 and the plan's Global Constraints.
"""

from __future__ import annotations

from app.memory.summarizer import DEFAULT_KEEP_LAST, should_summarize
from langchain_core.messages import AIMessage, HumanMessage


def test_short_but_token_heavy_history_triggers():
    """A few messages carrying large payloads trip the token branch.

    "Few" still has to exceed ``DEFAULT_KEEP_LAST``: below that nothing is removable
    and the branch is floored off on purpose (see the H1/D-3 regression tests at the
    bottom of this file). This fixture originally used 3 messages and passed, which is
    exactly how the no-progress loop went unnoticed.
    """
    big = "word " * 4000  # ~20k chars ⇒ ~5k tokens each
    msgs = [
        HumanMessage(content=big) if i % 2 == 0 else AIMessage(content=big)
        for i in range(DEFAULT_KEEP_LAST + 1)
    ]
    # Count threshold high enough to prove the count branch did NOT fire.
    assert should_summarize(msgs, threshold=50, token_budget=12000) is True


def test_token_payload_in_tool_calls_is_counted():
    """Tokens hidden in ``tool_calls`` args (not ``content``) still count."""
    heavy_args = {"payload": "x" * 60000}  # ~60k chars ⇒ ~15k tokens
    heavy = AIMessage(
        content="",  # empty content — all weight is in the tool call
        tool_calls=[
            {"name": "search", "args": heavy_args, "id": "call_1", "type": "tool_call"}
        ],
    )
    # Pad past DEFAULT_KEEP_LAST with near-empty messages so the weight under test is
    # still entirely in tool_calls, but something is actually removable.
    msgs = [HumanMessage(content="x") for _ in range(DEFAULT_KEEP_LAST)] + [heavy]
    assert should_summarize(msgs, threshold=50, token_budget=12000) is True


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


# --- Regressions found by correctness review (H1/D-3, D-2) -------------------


def test_token_branch_does_not_fire_when_nothing_is_removable():
    """H1/D-3: the token branch must not promise a compression that cannot happen.

    ``summarize_conversation`` keeps the last ``DEFAULT_KEEP_LAST`` messages, so with
    that many or fewer there is nothing to remove. Before the floor, a short-but-heavy
    history satisfied ``should_summarize`` forever: one paid summarizer call per turn,
    zero messages removed, the estimate unchanged, fires again next turn.
    """
    from app.memory.summarizer import _safe_split

    heavy = [HumanMessage(content="word " * 4000) for _ in range(3)]
    assert _safe_split(heavy, DEFAULT_KEEP_LAST) == 0  # nothing removable
    assert should_summarize(heavy) is False

    # One message past the floor, the same weight now legitimately compresses.
    heavy_enough = [
        HumanMessage(content="word " * 4000) for _ in range(DEFAULT_KEEP_LAST + 1)
    ]
    assert _safe_split(heavy_enough, DEFAULT_KEEP_LAST) > 0
    assert should_summarize(heavy_enough) is True


def test_summarize_conversation_skips_the_llm_call_when_nothing_is_removable():
    """H1/D-3, defence in depth: no removable message means no paid call."""
    from app.memory.summarizer import summarize_conversation

    class _Boom:
        def invoke(self, *a, **k):
            raise AssertionError("summarize_conversation must not call the LLM here")

    summary, to_remove = summarize_conversation(
        [HumanMessage(content="word " * 4000)], _Boom()
    )
    assert summary == ""
    assert to_remove == []


def test_staleness_rule_covers_every_non_fresh_bucket():
    """D-2: the rule must catch every aged bucket, not self-exclude one.

    The original wording was "anything recorded **more than a few months ago** should be
    confirmed", while `format_age` emitted the literal phrase "a few months ago" for the
    entire 1-11 month span — so an 11-month-old preference was told NOT to be confirmed,
    looser than the unqualified base text it replaced.

    The assertion is deliberately phrased against the DEFECT SHAPE rather than against
    that one historical string: any "more than <phrase>" construction re-excludes the
    bucket named by <phrase>. Pinning the old literal would have gone stale the moment
    the vocabulary changed — which it since has, twice.
    """
    from app.agents.state import system_with_summary
    from app.memory.store import AGE_FRESH, _AGE_COARSE, _AGE_FINE
    from langchain_core.messages import SystemMessage

    content = system_with_summary(
        {"preferences": "- diet: vegetarian (recorded 4-8 months ago)"},
        SystemMessage(content="BASE"),
    ).content

    # The rule keys off the ONE fresh marker, so every other phrase in either
    # vocabulary is in scope without the prompt having to enumerate them.
    assert f"recorded {AGE_FRESH}" in content
    assert "confirmed" in content

    # No aged phrase may appear after "more than", in either vocabulary.
    aged = [p for _, p in (*_AGE_COARSE, *_AGE_FINE) if p != AGE_FRESH]
    for phrase in aged:
        assert f"more than {phrase}" not in content, (
            f"the rule excludes the {phrase!r} bucket it is meant to catch"
        )


def test_summarize_conversation_merges_the_previous_summary():
    """H2: a repeated compression must not replace the rolling summary.

    The messages behind the old summary are already deleted, so replacing it loses
    those facts from both places at once.
    """
    from app.memory.summarizer import summarize_conversation

    seen = {}

    class _Capture:
        def invoke(self, msgs, *a, **k):
            seen["system"] = msgs[0].content
            seen["payload"] = msgs[1].content

            return AIMessage(content="merged")

    msgs = [HumanMessage(content=f"m{i}", id=str(i)) for i in range(10)]
    summary, to_remove = summarize_conversation(
        msgs, _Capture(), previous_summary="traveller is vegetarian; budget 20m VND"
    )

    assert summary == "merged"
    assert to_remove  # progress was made
    assert "vegetarian" in seen["payload"]  # the old summary reached the model
    assert "Summary so far" in seen["payload"]
    assert "at most 250 words" in seen["system"]  # merge prompt, with its growth cap
