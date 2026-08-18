"""PII guardrail tests (specs/pii-middleware-guardrail).

Covers the pure ``redact_pii`` function and the ``pii_guardrail_node`` in-place
replacement. Scope is email + credit card only; names and phones are asserted
UNTOUCHED (names are owned by MIN-53's post-response extractor).
"""

from app.agents.guardrails import pii_guardrail_node, redact_pii
from langchain_core.messages import AIMessage, HumanMessage

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


def test_masks_card_followed_by_expiry():
    # Regression: trailing expiry digits used to inflate the run past Luhn and
    # leak the whole card. The window search must still find + mask the card.
    out = redact_pii(f"card {VALID_CARD} 08/25")
    assert VALID_CARD not in out
    assert "****-****-****-1111" in out


def test_masks_card_with_dot_and_newline_separators():
    assert "4242424242424242" not in redact_pii("pay 4242.4242.4242.4242 now")
    assert "4242424242424242" not in redact_pii("pay 4242\n4242\n4242\n4242 now")


def test_masks_card_glued_to_letters():
    # No word boundary around the digits — must still be caught.
    assert "4111111111111111" not in redact_pii("mycardis4111111111111111ok")


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


def test_node_noop_when_no_id():
    # No id → can't replace in place via add_messages; must no-op, not append.
    out = pii_guardrail_node({"messages": [HumanMessage(content="a@b.com", id=None)]})
    assert out == {}


def test_node_noop_on_multimodal_content():
    # List (multimodal) content is out of scope; guard must no-op, not crash.
    multimodal = HumanMessage(content=[{"type": "text", "text": "a@b.com"}], id="m-1")
    assert pii_guardrail_node({"messages": [multimodal]}) == {}


def test_node_preserves_message_fields():
    original = HumanMessage(content="mail a@b.com", id="m-1", name="user-42")
    out = pii_guardrail_node({"messages": [original]})
    assert out["messages"][0].name == "user-42"


def test_node_targets_the_newest_human_message():
    msgs = [
        HumanMessage(content="old turn", id="h-1"),
        AIMessage(content="reply", id="a-1"),
        HumanMessage(content="my card is " + VALID_CARD, id="h-2"),
    ]
    out = pii_guardrail_node({"messages": msgs})
    assert out["messages"][0].id == "h-2"
    assert out["messages"][0].content == "my card is ****-****-****-1111"
