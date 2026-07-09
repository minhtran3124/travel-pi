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
    # concierge was bumped again to 9 by travel-knowledge-rag; planner/memory
    # stay at their MIN-53/MIN-60 versions.
    assert active["concierge"] == 9
    assert active["planner"] == 5
    assert active["memory_extraction"] == 4  # MIN-60 follow-up: name-capture guard
