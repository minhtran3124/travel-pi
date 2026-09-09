"""Concierge follow-up dedup instruction (MIN-50) and hotel-tool routing (gh-147, v12)."""


def test_concierge_prompt_mentions_exclude_names_on_followup():
    from app.prompts.registry import registry

    text = registry.get("concierge")
    assert "exclude_names" in text


def test_concierge_prompt_picks_the_right_hotel_tool():
    from app.prompts.registry import registry

    text = " ".join(registry.get("concierge").split())
    assert "never ask for dates, rooms or guests in order to browse" in text
    assert "already given you check-in and check-out" in text
    assert "You still do not book" in text
