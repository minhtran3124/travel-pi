"""Concierge follow-up dedup instruction (MIN-50)."""


def test_concierge_prompt_mentions_exclude_names_on_followup():
    from app.prompts.registry import registry

    text = registry.get("concierge")
    assert "exclude_names" in text


def test_concierge_prompt_names_the_visa_tool():
    from app.prompts.registry import registry

    text = registry.get("concierge")
    assert "get_visa" in text


def test_concierge_prompt_no_longer_denies_having_a_visa_source():
    from app.prompts.registry import registry

    text = registry.get("concierge")
    assert "no other source" not in text
