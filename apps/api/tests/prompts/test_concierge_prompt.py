"""Concierge follow-up dedup instruction (MIN-50)."""


def test_concierge_prompt_mentions_exclude_names_on_followup():
    from app.prompts.registry import registry

    text = registry.get("concierge")
    assert "exclude_names" in text
