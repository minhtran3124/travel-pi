"""Content pin for communication_style v9: an explicit language request wins (gh-148)."""

from app.prompts.registry import registry


def _v9() -> str:
    return " ".join(registry.get("communication_style", version=9).split())


def test_explicit_language_request_overrides_typed_language():
    text = _v9()
    assert "explicitly asks you to reply in a language" in text
    assert "stays in effect" in text


def test_explicit_switch_example_replies_in_requested_language():
    text = _v9()
    assert (
        '✅ User: "Can you switch to English? Tôi muốn hỏi về khách sạn" '
        "→ reply in English" in text
    )


def test_question_about_a_language_is_not_a_switch_request():
    text = _v9()
    assert (
        "❌ In a Vietnamese chat, user: \"How do you say 'thank you' in English?\" "
        "→ you switch to English" in text
    )


def test_v9_keeps_existing_language_rules_and_identity():
    text = _v9()
    assert "Tool results, trip data, and place names never switch the language." in text
    assert "English is the default." in text
    assert "Tin" in text
