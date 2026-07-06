"""PII guardrail tests (MIN-62 / specs/pii-guardrail-redaction).

Covers the pure ``redact_pii`` function, the ``pii_guardrail_node`` in-place
replacement, and end-to-end redaction through the compiled graph. Scope is
email + credit card only; names and phones are asserted UNTOUCHED (names are
owned by MIN-53's post-response extractor).
"""

from app.agents.graph import build_graph
from app.agents.guardrails import pii_guardrail_node, redact_pii
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

# A Luhn-valid test card (Visa). "1111 1111 1111 1111" is Luhn-INVALID.
VALID_CARD = "4111 1111 1111 1111"


# ---------------------------------------------------------------------------
# redact_pii — pure function
# ---------------------------------------------------------------------------


def test_redacts_email():
    assert redact_pii("reach me at john.doe@example.com please") == (
        "reach me at [REDACTED_EMAIL] please"
    )


def test_masks_valid_card_keeping_last4():
    assert redact_pii(f"card {VALID_CARD} exp") == "card ****-****-****-1111 exp"


def test_leaves_non_luhn_number_untouched():
    # 16 digits but not a valid card — must not be masked.
    text = "order 1111 1111 1111 1111 shipped"
    assert redact_pii(text) == text


def test_does_not_redact_name():
    # Names are captured by MIN-53's extractor; redacting would break it.
    text = "My name is John Smith and I love Da Nang"
    assert redact_pii(text) == text


def test_does_not_redact_phone():
    text = "call me on 0912345678"
    assert redact_pii(text) == text


def test_plain_text_and_empty_unchanged():
    assert redact_pii("just a normal trip question") == "just a normal trip question"
    assert redact_pii("") == ""


def test_email_and_card_together():
    out = redact_pii(f"mail a@b.co card {VALID_CARD}")
    assert "a@b.co" not in out
    assert VALID_CARD not in out
    assert "[REDACTED_EMAIL]" in out and "****-****-****-1111" in out


# ---------------------------------------------------------------------------
# pii_guardrail_node — in-place replacement
# ---------------------------------------------------------------------------


def test_node_replaces_latest_human_in_place():
    original = HumanMessage(content="email me at a@b.com", id="m-1")
    out = pii_guardrail_node({"messages": [original]})
    assert out["messages"][0].id == "m-1", "must reuse id so add_messages replaces"
    assert out["messages"][0].content == "email me at [REDACTED_EMAIL]"


def test_node_noop_when_no_pii():
    out = pii_guardrail_node({"messages": [HumanMessage(content="hello", id="m-1")]})
    assert out == {}


def test_node_noop_when_no_human_message():
    out = pii_guardrail_node({"messages": [AIMessage(content="hi", id="a-1")]})
    assert out == {}


def test_node_targets_the_newest_human_message():
    msgs = [
        HumanMessage(content="old turn", id="h-1"),
        AIMessage(content="reply", id="a-1"),
        HumanMessage(content="my card is " + VALID_CARD, id="h-2"),
    ]
    out = pii_guardrail_node({"messages": msgs})
    assert out["messages"][0].id == "h-2"
    assert out["messages"][0].content == "my card is ****-****-****-1111"


# ---------------------------------------------------------------------------
# End-to-end through the compiled graph
# ---------------------------------------------------------------------------


def _build(intent_target: str = "journal"):
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=intent_target)] * 6,
        responses=["done"] * 6,
    )
    fast = FakeLLM(responses=["OK"] * 6)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def test_graph_redacts_user_input_before_persisting():
    graph = _build()
    result = graph.invoke(
        {
            "messages": [HumanMessage(content="my email is secret@leak.com")],
            "user_id": "u1",
            "trip_id": None,
        },
        {"configurable": {"thread_id": "t-pii-1"}},
    )
    human = next(m for m in result["messages"] if isinstance(m, HumanMessage))
    assert "secret@leak.com" not in human.content
    assert "[REDACTED_EMAIL]" in human.content
