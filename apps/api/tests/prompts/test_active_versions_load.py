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
    # concierge was bumped again to 9 by travel-knowledge-rag; memory stays at
    # its MIN-60 version. planner→6 / booking→5 bumped by flight-search-date-context
    # (date resolution + multi-turn stitching reframe); booking→6 by
    # agent-date-resolution (dates go through the resolve_date tool, and are stated
    # rather than confirmed before a search). planner→7 is an intentional follow-up
    # bump within the same feature: code review found the booking v6 date rewrite
    # was never applied to planner, the dominant search path — this assert moving
    # 6→7 is the expected outcome of that fix, not an accidental drift.
    assert active["concierge"] == 9
    assert active["planner"] == 7
    assert active["booking"] == 6
    assert active["memory_extraction"] == 4  # MIN-60 follow-up: name-capture guard
