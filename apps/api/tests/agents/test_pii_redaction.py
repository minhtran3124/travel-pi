"""PII guardrail tests. Scope is credit card only; names, phones, and email are left untouched (email must reach the model for booking)."""

from app.agents.guardrails import pii_guardrail_node, redact_pii
from langchain_core.messages import AIMessage, HumanMessage

# Luhn-valid test card; "1111 1111 1111 1111" is Luhn-invalid.
VALID_CARD = "4111 1111 1111 1111"


def test_does_not_redact_email():
    # Email must survive so the model/booking tools see it.
    text = "reach me at john.doe@example.com please"
    assert redact_pii(text) == text


def test_masks_valid_card_keeping_last4():
    assert redact_pii(f"card {VALID_CARD} exp") == "card ****-****-****-1111 exp"


def test_leaves_non_luhn_number_untouched():
    text = "order 1111 1111 1111 1111 shipped"
    assert redact_pii(text) == text


def test_masks_card_followed_by_expiry():
    # Trailing expiry digits once inflated the run past Luhn and leaked the card.
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
    # Names are captured by the post-response extractor; redacting would break it.
    text = "My name is John Smith and I love Da Nang"
    assert redact_pii(text) == text


def test_does_not_redact_phone():
    text = "call me on 0912345678"
    assert redact_pii(text) == text


def test_plain_text_and_empty_unchanged():
    assert redact_pii("just a normal trip question") == "just a normal trip question"
    assert redact_pii("") == ""


def test_email_survives_card_still_masked():
    out = redact_pii(f"mail a@b.co card {VALID_CARD}")
    assert "a@b.co" in out
    assert VALID_CARD not in out
    assert "****-****-****-1111" in out


def test_node_replaces_latest_human_in_place():
    original = HumanMessage(content=f"card {VALID_CARD}", id="m-1")
    out = pii_guardrail_node({"messages": [original]})
    assert out["messages"][0].id == "m-1", "must reuse id so add_messages replaces"
    assert out["messages"][0].content == "card ****-****-****-1111"


def test_node_noop_on_email_only():
    # Email is no longer PII to the guardrail — no card present, so no-op.
    out = pii_guardrail_node({"messages": [HumanMessage(content="a@b.com", id="m-1")]})
    assert out == {}


def test_node_noop_when_no_pii():
    out = pii_guardrail_node({"messages": [HumanMessage(content="hello", id="m-1")]})
    assert out == {}


def test_node_noop_when_no_human_message():
    out = pii_guardrail_node({"messages": [AIMessage(content="hi", id="a-1")]})
    assert out == {}


def test_node_noop_when_no_id():
    # No id → can't replace in place via add_messages; must no-op, not append.
    out = pii_guardrail_node(
        {"messages": [HumanMessage(content=f"card {VALID_CARD}", id=None)]}
    )
    assert out == {}


def test_node_noop_on_multimodal_content():
    # List (multimodal) content is out of scope; guard must no-op, not crash.
    multimodal = HumanMessage(content=[{"type": "text", "text": VALID_CARD}], id="m-1")
    assert pii_guardrail_node({"messages": [multimodal]}) == {}


def test_node_preserves_message_fields():
    original = HumanMessage(content=f"card {VALID_CARD}", id="m-1", name="user-42")
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
