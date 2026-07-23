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


# ``test_min53_bumped_versions_active`` used to live here, asserting literal
# version numbers (concierge == 11, planner == 11, ...). It was removed: its
# stated purpose — "guard against an active.yaml typo" — is fully covered by
# the test above plus
# ``tests/api/prompts/test_prompt_registry_helpers.py::test_active_version_matches_active_yaml``,
# which asserts every active.yaml entry resolves to that exact version AND that
# the matching vN.md exists. Verified: pinning planner to a nonexistent v99
# fails there with "active.yaml pins planner to v99 but no v99.md exists".
#
# Pinning literals added no coverage and broke on every legitimate prompt bump
# (twice in two days), so its comment had grown into a changelog of past bumps.
