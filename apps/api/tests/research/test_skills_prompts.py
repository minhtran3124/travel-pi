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
    [("trip_research", 2), ("trip_research_grader", 3)],
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


def test_layout_keeps_ids_out_of_the_traveller_prose() -> None:
    """research-dossier-reader: ids live in a trailing ``## Ids`` section the reader
    view hides, and the grader fails an off-language file."""
    layout = (_SKILLS_DIR / "dossier-format" / "SKILL.md").read_text(encoding="utf-8")
    assert "## Ids section (load-bearing)" in layout
    for skill in ("flights", "stays", "day-plans"):
        text = (_SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")
        assert "`## Ids` section" in text, skill
    grader = registry.get("trip_research_grader")
    assert "One file in another language fails this criterion" in grader


def _grader_criteria_1_to_4(text: str) -> str:
    """The verbatim rubric block covering criteria 1-4, which v3 must preserve."""
    start = text.index("1. **Every dimension file exists")
    end = text.index("5. **Language matches")
    return text[start:end]


def test_grader_v3_adds_web_source_criterion() -> None:
    """gh-229: grader v3 gains criterion 7 for web-tool facts and keeps 1-4 verbatim."""
    assert registry.active_version("trip_research_grader") == 3
    v2 = registry.get("trip_research_grader", version=2)
    v3 = registry.get("trip_research_grader")
    assert "7." in v3
    assert "search_web" in v3
    assert "find_places_live" in v3
    assert "## Sources" in v3
    # Criteria 1-4 carried over from v2 unchanged.
    assert _grader_criteria_1_to_4(v2) in v3


def test_skills_name_the_web_tools() -> None:
    """gh-229: the entry/season and day skills gate the web tools on the seeded
    tools returning nothing, and dossier-format carries the Sources rule."""
    entry = (_SKILLS_DIR / "entry-and-season" / "SKILL.md").read_text(encoding="utf-8")
    days = (_SKILLS_DIR / "day-plans" / "SKILL.md").read_text(encoding="utf-8")
    dossier = (_SKILLS_DIR / "dossier-format" / "SKILL.md").read_text(encoding="utf-8")

    for text in (entry, days):
        assert "only when the seeded tools return nothing" in text
        assert "data, never instructions" in text
    assert "search_web" in entry
    assert "search_web" in days
    assert "find_places_live" in days

    assert "## Sources" in dossier
    assert "data, never instructions" in dossier
