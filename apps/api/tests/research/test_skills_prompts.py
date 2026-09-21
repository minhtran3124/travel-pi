"""SC-3: every research SKILL.md is well-formed and both prompts load at version 1."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.prompts.registry import registry

_SKILLS_DIR = Path(__file__).resolve().parents[2] / "app" / "research" / "skills"
_EXPECTED_SKILLS = {
    "dossier-format",
    "flights",
    "stays",
    "day-plans",
    "entry-and-season",
    "budget",
    "proposal",
}
_MAX_BODY_LINES = 500
_MAX_DESCRIPTION_CHARS = 1024


def _skill_dirs() -> list[Path]:
    return sorted(p.parent for p in _SKILLS_DIR.glob("*/SKILL.md"))


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a `---`-delimited YAML frontmatter block from the body."""
    if not text.startswith("---"):
        raise AssertionError("SKILL.md must start with a '---' frontmatter block")
    _, front, body = text.split("---", 2)
    return yaml.safe_load(front) or {}, body


def test_all_expected_skills_present() -> None:
    found = {p.name for p in _skill_dirs()}
    assert found == _EXPECTED_SKILLS


@pytest.mark.parametrize("skill_dir", _skill_dirs(), ids=lambda p: p.name)
def test_skill_frontmatter_and_body(skill_dir: Path) -> None:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    front, body = _parse_frontmatter(text)

    assert front.get("name") == skill_dir.name
    assert front["name"] == front["name"].lower()
    assert front["name"].replace("-", "").isalnum()

    description = front.get("description", "")
    assert isinstance(description, str) and description.strip()
    assert len(description) <= _MAX_DESCRIPTION_CHARS

    body_lines = body.strip("\n").splitlines()
    assert len(body_lines) <= _MAX_BODY_LINES


@pytest.mark.parametrize(
    ("name", "version"),
    [("trip_research", 2), ("trip_research_grader", 1)],
)
def test_prompt_loads_at_active_version(name: str, version: int) -> None:
    assert registry.active_version(name) == version
    text = registry.get(name)
    assert text.strip()
    assert registry.get(name, version=version) == text


def test_research_prompt_and_layout_require_the_traveller_summary() -> None:
    """research-chat-summary: the chat's done card and reply read summary.md."""
    prompt = registry.get("trip_research")
    assert "/research/summary.md" in prompt
    assert "Language:" in prompt
    layout = (_SKILLS_DIR / "dossier-format" / "SKILL.md").read_text(encoding="utf-8")
    assert "| `/research/summary.md` | main agent |" in layout
