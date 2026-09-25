"""Grader and reports (design §5.8).

`grade` runs one `claude_cli.run` per session against a fixed rubric, scoring
goal completion, fabrication, reply language, ask-not-assume, tool
appropriateness, and tone. `write_reports` renders the machine-readable
`report.json`, the failing-first `report.md`, and `candidates/golden_candidates.json`
in the evalkit golden shape (loadable through `evalkit.dataset.JsonDatasetStore`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sim import claude_cli
from sim.driver import BatchResult, SessionResult

_PROMPTS = Path(__file__).parent / "prompts"

_VERDICTS = ("pass", "warn", "fail")
_RANK = {"fail": 0, "warn": 1, "pass": 2}
_CANDIDATE_VERDICTS = ("fail", "warn")

_CRITERIA = (
    "goal_completion",
    "fabrication",
    "language_match",
    "asked_not_assumed",
    "tool_appropriateness",
    "tone",
)

_CRITERION_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "evidence": {"type": "string"},
    },
    "required": ["score", "evidence"],
}

GRADER_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(_VERDICTS)},
        "score": {"type": "number"},
        "summary": {"type": "string"},
        "criteria": {
            "type": "object",
            "properties": dict.fromkeys(_CRITERIA, _CRITERION_SCHEMA),
            "required": list(_CRITERIA),
        },
    },
    "required": ["verdict", "score", "criteria"],
}


@dataclass
class Grade:
    persona_id: str
    verdict: str
    score: float
    criteria: dict = field(default_factory=dict)
    summary: str = ""


def _read(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


def _dump(row: object) -> object:
    dump = getattr(row, "model_dump", None)
    return dump(mode="json") if callable(dump) else row


def _payload(
    session: SessionResult,
    db_rows: dict,
) -> dict:
    return {
        "persona": {
            "id": session.persona.id,
            "name": session.persona.name,
            "language": session.persona.language,
        },
        "status": session.status,
        "turns": session.turns,
        "tools": session.tools,
        "panels": session.panels,
        "db_check": {
            "bookings": [_dump(b) for b in db_rows.get("bookings", [])],
            "trips": [_dump(t) for t in db_rows.get("trips", [])],
        },
    }


async def grade(
    session: SessionResult,
    db_rows: dict,
) -> Grade:
    user_prompt = json.dumps(_payload(session, db_rows), ensure_ascii=False, indent=2)
    result = await claude_cli.run(_read("grader.md"), user_prompt, GRADER_SCHEMA)
    verdict = result.get("verdict")
    if verdict not in _VERDICTS:
        verdict = "fail"
    return Grade(
        persona_id=session.persona.id,
        verdict=verdict,
        score=float(result.get("score", 0.0)),
        criteria=result.get("criteria") or {},
        summary=str(result.get("summary", "")),
    )


def _capability(session: SessionResult) -> str:
    if session.tools:
        name = session.tools[0]
        if name == "search_flights":
            return "flight_search"
        if "hotel" in name:
            return "hotels"
        if name.startswith("book_"):
            return "booking"
        if "budget" in name:
            return "budget"
    if session.status == "bot_error":
        return "errors"
    return "routing"


def _scenario(session: SessionResult) -> str:
    return "tool_failure" if session.status == "bot_error" else "multi_turn"


def _candidate(
    batch_ts: str,
    session: SessionResult,
) -> dict:
    return {
        "id": f"sim-{batch_ts}-{session.persona.id}",
        "suite": "sim",
        "language": session.persona.language,
        "capability": _capability(session),
        "scenario": _scenario(session),
        "turns": [t["text"] for t in session.turns if t.get("role") == "user"],
    }


def _total_usage(sessions: list[SessionResult]) -> dict:
    total: dict = {}
    for session in sessions:
        for key, value in session.usage.items():
            if isinstance(value, (int, float)):
                total[key] = total.get(key, 0) + value
    return total


def _cli_version() -> str:
    try:
        return claude_cli.cli_version()
    except claude_cli.DriverError:
        return "unknown"


_FABRICATION_NOTE = (
    "Fabrication findings are limited to claims that contradict or go beyond "
    "`panel` data (and `db_check` rows): the SSE `tool_result` carries only a "
    "status, never its content, so a claim that cannot be checked against a "
    "panel is not counted as fabrication."
)


def _render_md(
    batch: BatchResult,
    ordered: list[Grade],
    usage: dict,
    version: str,
) -> str:
    lines = [
        "# Simulation report",
        "",
        f"- `claude -p` calls: {batch.claude_calls}",
        f"- Chatbot usage: {json.dumps(usage, ensure_ascii=False)}",
        f"- `claude` CLI version: {version}",
        "",
        _FABRICATION_NOTE,
        "",
        "| Persona | Verdict | Score | Transcript |",
        "|---|---|---|---|",
    ]
    for g in ordered:
        lines.append(
            f"| {g.persona_id} | {g.verdict} | {g.score:g} | transcript.jsonl |"
        )
    return "\n".join(lines) + "\n"


def write_reports(
    run_dir: str | Path,
    batch: BatchResult,
    grades: list[Grade],
) -> None:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    batch_ts = run_dir.name
    sessions_by_id = {s.persona.id: s for s in batch.sessions}
    ordered = sorted(grades, key=lambda g: _RANK.get(g.verdict, 0))
    usage = _total_usage(batch.sessions)
    version = _cli_version()

    report = {
        "batch_ts": batch_ts,
        "batch_status": batch.status,
        "claude_calls": batch.claude_calls,
        "usage": usage,
        "cli_version": version,
        "sessions": [
            {
                "persona_id": g.persona_id,
                "verdict": g.verdict,
                "score": g.score,
                "summary": g.summary,
                "criteria": g.criteria,
                "status": getattr(sessions_by_id.get(g.persona_id), "status", None),
            }
            for g in ordered
        ],
    }
    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(
        _render_md(batch, ordered, usage, version),
        encoding="utf-8",
    )

    candidates_dir = run_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        _candidate(batch_ts, sessions_by_id[g.persona_id])
        for g in ordered
        if g.verdict in _CANDIDATE_VERDICTS and g.persona_id in sessions_by_id
    ]
    (candidates_dir / "golden_candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
