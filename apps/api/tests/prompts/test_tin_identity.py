"""Chatbot branding: assistant identifies itself as Tin (MIN-60)."""


def test_communication_style_mentions_tin():
    from app.prompts.registry import registry

    text = registry.get("communication_style")
    assert "Tin" in text
