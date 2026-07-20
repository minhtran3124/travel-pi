"""Tests for PromptRegistry.versions() / active_version() (additive read helpers)."""

import pytest
import yaml
from app.prompts.registry import _ACTIVE_FILE, PromptRegistry, registry


def test_versions_returns_sorted_ints():
    assert registry.versions("budget") == [1, 2]


def test_active_version_matches_active_yaml():
    """Every name in active.yaml resolves to that exact version, and the
    corresponding vN.md exists.

    Asserted against active.yaml itself rather than a hardcoded number so a
    legitimate prompt bump doesn't fail the suite — while still catching the
    real failure mode: active.yaml pointing at a version that has no file.
    """
    active = yaml.safe_load(_ACTIVE_FILE.read_text(encoding="utf-8"))

    assert active, "active.yaml is empty"
    for name, version in active.items():
        assert registry.active_version(name) == version
        assert version in registry.versions(name), (
            f"active.yaml pins {name} to v{version} but no v{version}.md exists"
        )


def test_active_version_falls_back_to_max_when_absent_from_active_yaml(tmp_path):
    (tmp_path / "foo").mkdir()
    (tmp_path / "foo" / "v1.md").write_text("foo v1", encoding="utf-8")
    (tmp_path / "foo" / "v3.md").write_text("foo v3", encoding="utf-8")

    fresh = PromptRegistry(prompts_dir=tmp_path)

    assert fresh.versions("foo") == [1, 3]
    assert fresh.active_version("foo") == 3


def test_versions_unknown_name_raises_key_error():
    with pytest.raises(KeyError):
        registry.versions("nope")


def test_active_version_unknown_name_raises_key_error():
    with pytest.raises(KeyError):
        registry.active_version("nope")
