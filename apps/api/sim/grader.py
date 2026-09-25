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
    graded: bool = True


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


def _ungraded(
    session: SessionResult,
    summary: str,
) -> Grade:
    return Grade(
        persona_id=session.persona.id,
        verdict="fail",
        score=0.0,
        criteria={},
        summary=summary,
        graded=False,
    )


def _coerce_score(raw: object) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 5.0:
        return 5.0
    return value


async def grade(
    session: SessionResult,
    db_rows: dict,
) -> Grade:
    user_prompt = json.dumps(_payload(session, db_rows), ensure_ascii=False, indent=2)
    try:
        result = await claude_cli.run(_read("grader.md"), user_prompt, GRADER_SCHEMA)
        verdict = result.get("verdict")
        if verdict not in _VERDICTS:
            verdict = "fail"
        return Grade(
            persona_id=session.persona.id,
            verdict=verdict,
            score=_coerce_score(result.get("score")),
            criteria=result.get("criteria") or {},
            summary=str(result.get("summary", "")),
        )
    except claude_cli.QuotaExhausted:
        return _ungraded(session, "ungraded: quota exhausted")
    except claude_cli.DriverError:
        return _ungraded(session, "ungraded: grader claude -p failed")
    except Exception as exc:  # noqa: BLE001 - a grader crash must not lose reports
        return _ungraded(session, f"ungraded: grader error: {type(exc).__name__}")


def _capability(session: SessionResult) -> str:
    if any(name.startswith("book_") for name in session.tools):
        return "booking"
    if session.tools:
        name = session.tools[0]
        if name == "search_flights":
            return "flight_search"
        if "hotel" in name:
            return "hotels"
        if "budget" in name:
            return "budget"
    if session.status == "bot_error":
        return "errors"
    return "routing"


def _scenario(session: SessionResult) -> str:
    return "tool_failure" if session.status == "bot_error" else "multi_turn"


def _has_user_turn(session: SessionResult) -> bool:
    return any(t.get("role") == "user" for t in session.turns)


_RESUME_MARKER = "[resume approved="


def _candidate(
    batch_ts: str,
    session: SessionResult,
) -> dict:
    user_turns = [t for t in session.turns if t.get("role") == "user"]
    resume = next(
        (t for t in user_turns if t["text"].startswith(_RESUME_MARKER)),
        None,
    )
    candidate = {
        "id": f"sim-{batch_ts}-{session.persona.id}",
        "suite": "full",
        "language": session.persona.language,
        "capability": _capability(session),
        "scenario": _scenario(session),
        "turns": [
            t["text"] for t in user_turns if not t["text"].startswith(_RESUME_MARKER)
        ],
    }
    if resume is not None:
        candidate["hitl"] = "approve" if "approved=True" in resume["text"] else "reject"
    return candidate


def _total_usage(sessions: list[SessionResult]) -> dict:
    total: dict = {}
    for session in sessions:
        for key, value in session.usage.items():
            if isinstance(value, (int, float)):
                total[key] = total.get(key, 0) + value
    return total


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
        "Transcript links carry the `persona_id` to grep in `transcript.jsonl`; "
        "true per-session line ranges are deferred.",
        "",
        _FABRICATION_NOTE,
        "",
        "Golden candidates below carry no expectations or metrics; add "
        "`expected_*`/`oracle_checks`/`metrics` during human review before "
        "promoting them into an eval dataset.",
        "",
        "| Persona | Verdict | Score | Transcript |",
        "|---|---|---|---|",
    ]
    for g in ordered:
        transcript = f"transcript.jsonl (persona_id={g.persona_id})"
        verdict = g.verdict if g.graded else "ungraded"
        lines.append(f"| {g.persona_id} | {verdict} | {g.score:g} | {transcript} |")
    return "\n".join(lines) + "\n"


def write_reports(
    run_dir: str | Path,
    batch: BatchResult,
    grades: list[Grade],
    cli_version: str = "unknown",
) -> None:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    batch_ts = run_dir.name
    sessions_by_id = {s.persona.id: s for s in batch.sessions}
    ordered = sorted(grades, key=lambda g: (g.graded, _RANK.get(g.verdict, 0)))
    usage = _total_usage(batch.sessions)
    version = cli_version

    report = {
        "batch_ts": batch_ts,
        "batch_status": batch.status,
        "claude_calls": batch.claude_calls,
        "usage": usage,
        "cli_version": version,
        "sessions": [
            {
                "persona_id": g.persona_id,
                "verdict": g.verdict if g.graded else "ungraded",
                "graded": g.graded,
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
        if g.graded
        and g.verdict in _CANDIDATE_VERDICTS
        and g.persona_id in sessions_by_id
        and _has_user_turn(sessions_by_id[g.persona_id])
    ]
    (candidates_dir / "golden_candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
