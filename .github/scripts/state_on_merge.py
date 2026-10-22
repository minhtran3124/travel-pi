#!/usr/bin/env python3
"""Mark a spec shipped after its pull request merges into main.

Run by .github/workflows/state-on-merge.yml. It appends the
`ready_to_merge -> shipped` event to specs/<slug>/events.jsonl, rewrites
specs/<slug>/RUN.json, and refreshes specs/STATE.md.

Stdlib only and self-contained: the harness engine (.claude/runtime/run_state.py)
is excluded from git, so CI cannot import it. The event written here and the
RUN.json projection follow that engine's chain invariants and project() exactly,
so a local `run_state.py status` keeps reading the run as consistent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)
RUN_JSON_RE = re.compile(r"^specs/([^/]+)/RUN\.json$")
BRANCH_TYPE_RE = re.compile(r"^[A-Za-z]+/")
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
COMMENT_RE = re.compile(r"<!--.*?-->")


def resolve_slug(
    changed_files: list[str], head_ref: str, root: Path
) -> tuple[str, bool] | None:
    """Return (slug, matched_branch) for a merged PR, or None when it has no spec.

    matched_branch is False when only a RUN.json in the diff named the slug; the
    caller then ships the run only if its own ready_to_merge event names this PR.
    """
    run_slugs = sorted(
        {m.group(1) for f in changed_files if (m := RUN_JSON_RE.match(f.strip()))}
    )
    from_branch = BRANCH_TYPE_RE.sub("", head_ref or "", count=1)
    if from_branch in run_slugs:
        return from_branch, True
    if (
        from_branch
        and "/" not in from_branch
        and (root / "specs" / from_branch).is_dir()
    ):
        return from_branch, True
    if len(run_slugs) == 1:
        return run_slugs[0], False
    return None


def project(events: list[dict]) -> dict:
    """Mirror of run_state.project(): fold an event list into the RUN.json projection."""
    first = events[0]
    state = first["to_state"]
    waiting_on = first.get("waiting_on")
    resume_event = first.get("resume_event")
    sha = first.get("sha")
    runtime_mode = runtime_evidence_id = None
    first_metadata = first.get("metadata")
    if isinstance(first_metadata, dict):
        runtime_mode = first_metadata.get("runtime_mode")
        runtime_evidence_id = first_metadata.get("runtime_evidence_id")
    for ev in events[1:]:
        state = ev["to_state"]
        waiting_on = ev.get("waiting_on")
        resume_event = ev.get("resume_event")
        if ev.get("sha"):
            sha = ev["sha"]
        metadata = ev.get("metadata")
        if isinstance(metadata, dict) and "runtime_mode" in metadata:
            runtime_mode = metadata.get("runtime_mode")
            runtime_evidence_id = metadata.get("runtime_evidence_id")
    last = events[-1]
    result = {
        "slug": first["slug"],
        "run_id": first["run_id"],
        "state": state,
        "seq": last["seq"],
        "waiting_on": waiting_on,
        "resume_event": resume_event,
        "sha": sha,
        "created_at": first["ts"],
        "updated_at": last["ts"],
        "last_event_id": last["event_id"],
    }
    if runtime_mode is not None and runtime_evidence_id is not None:
        result["runtime_mode"] = runtime_mode
        result["runtime_evidence_id"] = runtime_evidence_id
    return result


def mark_shipped(
    spec_dir: Path, slug: str, pr: int, sha: str, now: str, require_pr: bool = False
) -> str:
    """Append the ready_to_merge -> shipped event and rewrite RUN.json.

    Returns a short outcome string; never raises for a run that is simply not
    ready (the merge already happened, so there is nothing to block).
    """
    events_file = spec_dir / "events.jsonl"
    if not events_file.is_file():
        return "no run (events.jsonl missing)"
    events = [
        json.loads(line)
        for line in events_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not events:
        return "no run (events.jsonl empty)"
    event_id = f"pr-{pr}-merged"
    last = events[-1]
    if last.get("to_state") == "shipped" or any(
        e.get("event_id") == event_id for e in events
    ):
        return "already shipped"
    if last.get("to_state") != "ready_to_merge":
        return f"left at {last.get('to_state')} (only ready_to_merge can ship)"
    # Many older runs still sit at ready_to_merge after their own merge; never let a
    # later PR that merely touches one of them ship it under the wrong PR and sha.
    opened_for = (last.get("metadata") or {}).get("pr")
    if (opened_for is not None and str(opened_for) != str(pr)) or (
        opened_for is None and require_pr
    ):
        return f"left at ready_to_merge (opened for PR #{opened_for}, not #{pr})"
    event = {
        "event": "pr.merged",
        "event_id": event_id,
        "from_state": "ready_to_merge",
        "metadata": {"pr": str(pr)},
        "resume_event": None,
        "run_id": events[0]["run_id"],
        "seq": last["seq"] + 1,
        "sha": sha,
        "slug": events[0]["slug"],
        "to_state": "shipped",
        "ts": now,
        "waiting_on": None,
    }
    with events_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
    events.append(event)
    (spec_dir / "RUN.json").write_text(
        json.dumps(project(events), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return "shipped"


def _section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return None
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return start, end


def _update_recent_specs(
    lines: list[str], slug: str, pr: int, sha7: str, created: str
) -> None:
    bounds = _section_bounds(lines, "## Recent Specs")
    if bounds is None:
        return
    start, end = bounds
    merged = f"merged via PR #{pr} → main ({sha7})"
    for i in range(start, end):
        cells = CELL_SPLIT_RE.split(lines[i])
        if len(cells) >= 6 and cells[1].strip() == slug:
            status = cells[4].strip()
            if f"PR #{pr}" not in status:
                status = f"{merged}; {status}" if status else merged
            cells[3] = " shipped "
            cells[4] = f" {status} "
            lines[i] = "|".join(cells)
            return
    separator = next(
        (i for i in range(start, end) if re.match(r"^\|\s*-{3,}", lines[i])), None
    )
    if separator is not None:
        lines.insert(separator + 1, f"| {slug} | {created} | shipped | {merged} |")


def _update_active_spec(
    lines: list[str], slug: str, pr: int, sha7: str, today: str
) -> None:
    bounds = _section_bounds(lines, "## Active Spec")
    if bounds is None:
        return
    start, end = bounds
    slug_line = next(
        (i for i in range(start, end) if re.match(r"^- \*\*Slug:\*\*", lines[i])), None
    )
    if (
        slug_line is None
        or COMMENT_RE.sub("", lines[slug_line].split("**Slug:**", 1)[1]).strip() != slug
    ):
        return
    i = start
    while i < end:
        line = lines[i]
        if re.match(r"^- \*\*Phase:\*\*", line):
            lines[i] = re.sub(r"(\*\*Phase:\*\*\s*)\S+", r"\1shipped", line, count=1)
        elif re.match(r"^- \*\*Updated:\*\*", line):
            lines[i] = f"- **Updated:** {today}"
        elif re.match(r"^- \*\*Last action:\*\*", line):
            j = i + 1
            while j < end and lines[j].startswith((" ", "\t")) and lines[j].strip():
                j += 1
            lines[i:j] = [
                f"- **Last action:** PR #{pr} merged → main ({sha7}); marked shipped by the "
                "state-on-merge workflow."
            ]
            end -= j - i - 1
        i += 1


def update_state_md(
    text: str, slug: str, pr: int, sha7: str, today: str, created: str
) -> str:
    """Refresh the Recent Specs row (always) and the Active Spec block (same slug only)."""
    lines = text.split("\n")
    _update_recent_specs(lines, slug, pr, sha7, created)
    _update_active_spec(lines, slug, pr, sha7, today)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--sha", required=True, help="merge commit sha")
    parser.add_argument("--head-ref", default="")
    parser.add_argument(
        "--changed-files", required=True, help="file, one path per line"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--now", help="UTC ISO timestamp (tests)")
    args = parser.parse_args(argv)

    if not SHA_RE.match(args.sha):
        print(f"error: --sha {args.sha!r} is not a git sha", file=sys.stderr)
        return 2
    root = Path(args.root)
    changed = Path(args.changed_files).read_text(encoding="utf-8").splitlines()
    resolved = resolve_slug(changed, args.head_ref, root)
    if resolved is None:
        print(f"PR #{args.pr}: no spec found; nothing to update.")
        return 0
    slug, matched_branch = resolved

    now = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    spec_dir = root / "specs" / slug
    outcome = mark_shipped(
        spec_dir, slug, args.pr, args.sha, now, require_pr=not matched_branch
    )
    print(f"{slug}: run {outcome}")
    if outcome not in ("shipped", "already shipped"):
        # No shipped run to back it: leave STATE.md alone rather than claim "shipped".
        print(f"{slug}: STATE.md left unchanged")
        return 0

    state_file = root / "specs" / "STATE.md"
    if state_file.is_file():
        created = now[:10]
        run_file = spec_dir / "RUN.json"
        if run_file.is_file():
            created = str(
                json.loads(run_file.read_text(encoding="utf-8")).get("created_at", now)
            )[:10]
        old = state_file.read_text(encoding="utf-8")
        new = update_state_md(old, slug, args.pr, args.sha[:7], now[:10], created)
        if new != old:
            state_file.write_text(new, encoding="utf-8")
            print(f"{slug}: STATE.md updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
