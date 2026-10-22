"""Tests for state_on_merge.py (run: .venv/bin/python -m pytest .github/scripts -q)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import state_on_merge as som  # noqa: E402

SHA = "7dfa67500e2a1e16c7c41e369bc58c46a26adccb"
NOW = "2026-09-16T01:02:03Z"
SLUG = "demo-spec"


def _chain(to_state: str = "ready_to_merge") -> list[dict]:
    """A legal engine chain ending at `to_state` (queued → … → ready_to_merge)."""
    hops = [
        (None, "queued"),
        ("queued", "investigating"),
        ("investigating", "planning"),
        ("planning", "implementing"),
        ("implementing", "verifying"),
        ("verifying", "ready_to_merge"),
    ]
    events = []
    for seq, (frm, to) in enumerate(hops, start=1):
        events.append(
            {
                "event": f"e{seq}",
                "event_id": f"id-{seq}",
                "from_state": frm,
                "metadata": {},
                "resume_event": None,
                "run_id": "run-1",
                "seq": seq,
                "sha": "abc1234" if seq == 6 else None,
                "slug": SLUG,
                "to_state": to,
                "ts": f"2026-09-15T00:00:0{seq}Z",
                "waiting_on": None,
            }
        )
        if to == to_state:
            break
    return events


def _spec(root: Path, events: list[dict]) -> Path:
    spec = root / "specs" / SLUG
    spec.mkdir(parents=True)
    (spec / "events.jsonl").write_text(
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in events)
    )
    (spec / "RUN.json").write_text(
        json.dumps(som.project(events), indent=2, sort_keys=True) + "\n"
    )
    return spec


def _load_engine():
    path = REPO / ".claude" / "runtime" / "run_state.py"
    if not path.is_file():
        pytest.skip(
            ".claude/runtime/run_state.py is not present (harness is not in git)"
        )
    spec = importlib.util.spec_from_file_location("run_state_engine", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- resolve_slug -------------------------------------------------------------


def test_resolve_slug_from_changed_run_json(tmp_path):
    files = ["apps/api/x.py", f"specs/{SLUG}/RUN.json", f"specs/{SLUG}/PLAN.md"]
    assert som.resolve_slug(files, "fix/whatever", tmp_path) == (SLUG, False)


def test_resolve_slug_falls_back_to_branch_when_spec_dir_exists(tmp_path):
    (tmp_path / "specs" / SLUG).mkdir(parents=True)
    assert som.resolve_slug(["README.md"], f"feat/{SLUG}", tmp_path) == (SLUG, True)


def test_resolve_slug_none_for_chore_branch_without_spec(tmp_path):
    assert (
        som.resolve_slug(["specs/STATE.md"], "chore/state-md-2026-09-15", tmp_path)
        is None
    )


def test_resolve_slug_ambiguous_run_json_uses_branch_or_skips(tmp_path):
    files = [f"specs/{SLUG}/RUN.json", "specs/other/RUN.json"]
    assert som.resolve_slug(files, f"feat/{SLUG}", tmp_path) == (SLUG, True)
    assert som.resolve_slug(files, "feat/unrelated", tmp_path) is None


# --- mark_shipped -------------------------------------------------------------


def test_mark_shipped_appends_event_and_rewrites_run_json(tmp_path):
    spec = _spec(tmp_path, _chain())
    assert som.mark_shipped(spec, SLUG, 42, SHA, NOW) == "shipped"
    lines = (spec / "events.jsonl").read_text().splitlines()
    last = json.loads(lines[-1])
    assert last["from_state"] == "ready_to_merge"
    assert last["to_state"] == "shipped"
    assert last["seq"] == 7
    assert last["sha"] == SHA
    assert last["event_id"] == "pr-42-merged"
    assert last["metadata"] == {"pr": "42"}
    run = json.loads((spec / "RUN.json").read_text())
    assert run["state"] == "shipped"
    assert run["sha"] == SHA
    assert run["last_event_id"] == "pr-42-merged"
    assert run["updated_at"] == NOW


def test_mark_shipped_is_idempotent(tmp_path):
    spec = _spec(tmp_path, _chain())
    som.mark_shipped(spec, SLUG, 42, SHA, NOW)
    before = (spec / "events.jsonl").read_text()
    assert som.mark_shipped(spec, SLUG, 42, SHA, NOW) == "already shipped"
    assert (spec / "events.jsonl").read_text() == before


def test_mark_shipped_leaves_a_run_that_is_not_ready(tmp_path):
    spec = _spec(tmp_path, _chain("verifying"))
    before = (spec / "events.jsonl").read_text()
    assert som.mark_shipped(spec, SLUG, 42, SHA, NOW).startswith("left at verifying")
    assert (spec / "events.jsonl").read_text() == before


def test_mark_shipped_refuses_a_run_opened_for_another_pr(tmp_path):
    events = _chain()
    events[-1]["metadata"] = {"pr": "142"}
    spec = _spec(tmp_path, events)
    before = (spec / "events.jsonl").read_text()
    assert som.mark_shipped(spec, SLUG, 999, SHA, NOW).startswith(
        "left at ready_to_merge"
    )
    assert (spec / "events.jsonl").read_text() == before
    assert som.mark_shipped(spec, SLUG, 142, SHA, NOW) == "shipped"


def test_mark_shipped_require_pr_skips_run_without_pr_metadata(tmp_path):
    spec = _spec(tmp_path, _chain())
    assert som.mark_shipped(spec, SLUG, 42, SHA, NOW, require_pr=True).startswith(
        "left at ready_to_merge"
    )


def test_mark_shipped_without_run(tmp_path):
    spec = tmp_path / "specs" / SLUG
    spec.mkdir(parents=True)
    assert som.mark_shipped(spec, SLUG, 42, SHA, NOW).startswith("no run")


def test_engine_accepts_written_chain_and_projection(tmp_path, monkeypatch):
    engine = _load_engine()
    spec = _spec(tmp_path, _chain())
    som.mark_shipped(spec, SLUG, 42, SHA, NOW)
    monkeypatch.chdir(tmp_path)
    events = engine.read_events(SLUG, validate=False)
    engine.validate_chain(events, SLUG, engine.events_path(SLUG))
    assert engine.project(events) == json.loads((spec / "RUN.json").read_text())


def test_engine_accepts_real_repo_chain_shipped(tmp_path, monkeypatch):
    """A tracked, real run truncated at ready_to_merge ships cleanly under the engine."""
    engine = _load_engine()
    source = REPO / "specs" / "gh-200-duplicate-warning-polish" / "events.jsonl"
    if not source.is_file():
        pytest.skip("fixture run not present")
    real = []
    for line in source.read_text().splitlines():
        real.append(json.loads(line))
        if real[-1]["to_state"] == "ready_to_merge":
            break
    slug = real[0]["slug"]
    spec = tmp_path / "specs" / slug
    spec.mkdir(parents=True)
    (spec / "events.jsonl").write_text(
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in real)
    )
    assert som.mark_shipped(spec, slug, 206, SHA, NOW) == "shipped"
    monkeypatch.chdir(tmp_path)
    events = engine.read_events(slug, validate=False)
    engine.validate_chain(events, slug, engine.events_path(slug))
    assert engine.project(events) == json.loads((spec / "RUN.json").read_text())


# --- update_state_md ----------------------------------------------------------

STATE = """# Workflow State

## Active Spec

- **Slug:** demo-spec
- **Phase:** review  <!-- design | research | plan | implement | review | shipped -->
- **Last skill:** finishing-a-development-branch
- **Last action:** opened PR; waiting for review
  continuation line of the old note.
- **Updated:** 2026-09-10

## Recent Specs

<!-- Populated as specs are created. Keep last 10. -->

| Slug | Created | Last phase | Status |
|---|---|---|---|
| demo-spec | 2026-09-10 | review | PR open; awaiting review |
| older | 2026-09-01 | shipped | merged via PR #1 → main (aaaaaaa) |

## Notes

- keep me
"""


def test_update_state_md_refreshes_row_and_matching_active_spec():
    out = som.update_state_md(STATE, SLUG, 42, SHA[:7], "2026-09-16", "2026-09-10")
    assert (
        "| demo-spec | 2026-09-10 | shipped | merged via PR #42 → main (7dfa675); "
        "PR open; awaiting review |" in out
    )
    assert "- **Phase:** shipped  <!-- design" in out
    assert "- **Last action:** PR #42 merged → main (7dfa675); marked shipped" in out
    assert "continuation line of the old note" not in out
    assert "- **Updated:** 2026-09-16" in out
    assert "- **Last skill:** finishing-a-development-branch" in out
    assert "| older | 2026-09-01 | shipped | merged via PR #1 → main (aaaaaaa) |" in out
    assert out.endswith("- keep me\n")


def test_update_state_md_leaves_other_active_spec_alone():
    text = STATE.replace("- **Slug:** demo-spec", "- **Slug:** something-else")
    out = som.update_state_md(text, SLUG, 42, SHA[:7], "2026-09-16", "2026-09-10")
    active = out.split("## Recent Specs")[0]
    assert active == text.split("## Recent Specs")[0]
    assert "| demo-spec | 2026-09-10 | shipped | merged via PR #42" in out


def test_update_state_md_inserts_missing_row_at_top():
    out = som.update_state_md(
        STATE, "new-spec", 43, SHA[:7], "2026-09-16", "2026-09-14"
    )
    rows = [line for line in out.splitlines() if line.startswith("| ")]
    assert (
        rows[1]
        == "| new-spec | 2026-09-14 | shipped | merged via PR #43 → main (7dfa675) |"
    )


def test_update_state_md_keeps_escaped_pipes_in_a_cell():
    text = STATE.replace("PR open; awaiting review", r"a \| b")
    out = som.update_state_md(text, SLUG, 42, SHA[:7], "2026-09-16", "2026-09-10")
    assert r"| shipped | merged via PR #42 → main (7dfa675); a \| b |" in out


def test_update_state_md_matches_slug_with_trailing_comment():
    text = STATE.replace(
        "- **Slug:** demo-spec", "- **Slug:** demo-spec  <!-- active -->"
    )
    out = som.update_state_md(text, SLUG, 42, SHA[:7], "2026-09-16", "2026-09-10")
    assert "- **Phase:** shipped" in out


def test_update_state_md_is_idempotent():
    once = som.update_state_md(STATE, SLUG, 42, SHA[:7], "2026-09-16", "2026-09-10")
    assert (
        som.update_state_md(once, SLUG, 42, SHA[:7], "2026-09-16", "2026-09-10") == once
    )


# --- main ---------------------------------------------------------------------


def test_main_end_to_end(tmp_path, capsys):
    _spec(tmp_path, _chain())
    (tmp_path / "specs" / "STATE.md").write_text(STATE)
    changed = tmp_path / "files.txt"
    changed.write_text(f"specs/{SLUG}/RUN.json\n")
    argv = [
        "--pr",
        "42",
        "--sha",
        SHA,
        "--head-ref",
        f"feat/{SLUG}",
        "--changed-files",
        str(changed),
        "--root",
        str(tmp_path),
        "--now",
        NOW,
    ]
    assert som.main(argv) == 0
    assert "demo-spec: run shipped" in capsys.readouterr().out
    assert (
        "| demo-spec | 2026-09-10 | shipped | merged via PR #42"
        in (tmp_path / "specs" / "STATE.md").read_text()
    )
    assert som.main(argv) == 0  # re-run is a no-op
    assert "already shipped" in capsys.readouterr().out


def test_main_leaves_state_md_when_no_run_ships(tmp_path, capsys):
    (tmp_path / "specs" / SLUG).mkdir(parents=True)  # spec dir, but no events.jsonl
    (tmp_path / "specs" / "STATE.md").write_text(STATE)
    changed = tmp_path / "files.txt"
    changed.write_text(f"specs/{SLUG}/PLAN.md\n")
    argv = [
        "--pr",
        "42",
        "--sha",
        SHA,
        "--head-ref",
        f"feat/{SLUG}",
        "--changed-files",
        str(changed),
        "--root",
        str(tmp_path),
        "--now",
        NOW,
    ]
    assert som.main(argv) == 0
    assert "STATE.md left unchanged" in capsys.readouterr().out
    assert (tmp_path / "specs" / "STATE.md").read_text() == STATE


def test_main_skips_pr_without_spec(tmp_path, capsys):
    changed = tmp_path / "files.txt"
    changed.write_text("README.md\n")
    argv = [
        "--pr",
        "7",
        "--sha",
        SHA,
        "--head-ref",
        "docs/readme",
        "--changed-files",
        str(changed),
        "--root",
        str(tmp_path),
    ]
    assert som.main(argv) == 0
    assert "nothing to update" in capsys.readouterr().out


def test_main_rejects_bad_sha(tmp_path):
    changed = tmp_path / "files.txt"
    changed.write_text("")
    assert (
        som.main(["--pr", "7", "--sha", "not-a-sha", "--changed-files", str(changed)])
        == 2
    )


# --- workflow -----------------------------------------------------------------


def test_workflow_triggers_on_merged_same_repo_prs_with_scoped_write():
    wf = yaml.safe_load(
        (REPO / ".github" / "workflows" / "state-on-merge.yml").read_text()
    )
    trigger = (
        wf[True] if True in wf else wf["on"]
    )  # PyYAML reads the bare `on` key as True
    assert trigger["pull_request"] == {"types": ["closed"], "branches": ["main"]}
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["mark-shipped"]
    assert "github.event.pull_request.merged == true" in job["if"]
    assert "head.repo.full_name == github.repository" in job["if"]
    assert job["permissions"]["contents"] == "write"
    for step in job["steps"]:
        # untrusted PR fields must arrive via env, never inline in the script
        assert "${{" not in step.get("run", ""), step.get("name")
    script_step = next(
        s for s in job["steps"] if "state_on_merge.py" in s.get("run", "")
    )
    assert script_step["env"]["HEAD_REF"] == "${{ github.event.pull_request.head.ref }}"
