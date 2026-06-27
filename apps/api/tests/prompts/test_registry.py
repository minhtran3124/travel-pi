"""Prompt registry (specs/travel-agent Task 1.2)."""

import pytest


def test_get_returns_active_version():
    from app.prompts.registry import registry

    text = registry.get("supervisor")
    assert "route" in text.lower()
    assert "planner" in text


def test_explicit_version():
    from app.prompts.registry import registry

    assert registry.get("supervisor", version=2) == registry.get("supervisor")


def test_unknown_name_raises():
    from app.prompts.registry import registry

    with pytest.raises(KeyError):
        registry.get("does-not-exist")


def test_unknown_version_raises():
    from app.prompts.registry import registry

    with pytest.raises(KeyError):
        registry.get("supervisor", version=99)


def test_names_lists_seeded_prompts():
    from app.prompts.registry import registry

    names = registry.names()
    assert "supervisor" in names
    assert "concierge" in names


def test_reload_picks_up_new_file(tmp_path):
    from app.prompts.registry import PromptRegistry

    (tmp_path / "greeting").mkdir()
    (tmp_path / "greeting" / "v1.md").write_text("hello v1", encoding="utf-8")
    (tmp_path / "active.yaml").write_text("greeting: 1\n", encoding="utf-8")
    reg = PromptRegistry(prompts_dir=tmp_path)
    assert reg.get("greeting") == "hello v1"

    (tmp_path / "greeting" / "v2.md").write_text("hello v2", encoding="utf-8")
    (tmp_path / "active.yaml").write_text("greeting: 2\n", encoding="utf-8")
    reg.reload()
    assert reg.get("greeting") == "hello v2"
    assert reg.get("greeting", version=1) == "hello v1"
