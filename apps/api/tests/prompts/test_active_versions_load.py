"""Smoke test: every active.yaml entry resolves to nonempty prompt text (MIN-53)."""


def test_every_active_version_loads_nonempty():
    from pathlib import Path

    import yaml
    from app.prompts.registry import registry

    active = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "app/prompts/active.yaml").read_text()
    )
    for name in active:
        text = registry.get(name)
        assert text and text.strip(), f"active prompt {name} loaded empty"


def test_min53_bumped_versions_active():
    """Guard against an active.yaml typo — the three bumped names resolve to the new versions."""
    from pathlib import Path

    import yaml

    active = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "app/prompts/active.yaml").read_text()
    )
    # concierge was bumped to 9 by travel-knowledge-rag. planner→6 / booking→5
    # bumped by flight-search-date-context (date resolution + multi-turn
    # stitching reframe); booking→6 by agent-date-resolution (dates go through
    # the resolve_date tool, and are stated rather than confirmed before a
    # search). planner→7 was an intentional follow-up: code review found the
    # booking v6 date rewrite was never applied to planner, the dominant
    # search path. memory_extraction stayed at 4 through MIN-60 (name-capture
    # guard). MIN-65 (chatbot intelligence: memory/reasoning/suggestions)
    # bumped all four again: concierge→10 / planner→8 / booking→7 add
    # ask-only-missing + reason-giving guidance (planner also gains
    # default-with-confirm for tool-optional args; booking explicitly does
    # NOT, since every book_* arg must stay traveller-supplied); memory_
    # extraction→5 adds the canonical-key vocabulary that curbs preference
    # key-drift duplication in the store. agent-trip-context bumped planner→9:
    # trip_id is now injected (never asked of / shown to the traveller) and the
    # planner opens a trip via create_trip when none is active.
    assert active["concierge"] == 10
    assert active["planner"] == 9
    assert active["booking"] == 7
    assert active["memory_extraction"] == 5
