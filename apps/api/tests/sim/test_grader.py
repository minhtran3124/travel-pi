"""Grader + reports tests (offline: fake claude_cli.run, fixture SessionResults)."""

from __future__ import annotations

import asyncio
import json

import pytest
from eval.adapters.config import TAXONOMY
from evalkit.dataset import JsonDatasetStore
from sim import claude_cli, grader
from sim.driver import BatchResult, SessionResult
from sim.personas import Persona


def _persona(pid, language="en"):
    return Persona.model_validate(
        {
            "id": pid,
            "name": f"Trav {pid}",
            "language": language,
            "budget": {"amount": 1000, "currency": "USD"},
            "trip_goal": {"destination": "Tokyo", "party_size": 2},
            "style": "terse",
            "will_book": True,
            "max_turns": 5,
        }
    )


def _session(pid, tools, status="done", language="en"):
    return SessionResult(
        persona=_persona(pid, language),
        conversation_id=f"conv-{pid}",
        status=status,
        turns=[
            {"role": "user", "text": f"{pid} asks for a flight"},
            {"role": "bot", "text": "Here you go"},
        ],
        tools=tools,
        panels=[{"kind": "flights", "items": []}],
        usage={"total_tokens": 10},
    )


def _fake_run_factory():
    async def run(system_prompt, user_prompt, schema, model=None, timeout=120):
        payload = json.loads(user_prompt)
        pid = payload["persona"]["id"]
        verdict = "fail" if pid == "flyer" else "pass"
        return {
            "verdict": verdict,
            "score": 1.0 if verdict == "fail" else 5.0,
            "summary": f"{pid} {verdict}",
            "criteria": {
                c: {"score": 1.0, "evidence": "quote"} for c in grader._CRITERIA
            },
        }

    return run


def test_reports_fail_first_and_candidate_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_cli, "run", _fake_run_factory())
    monkeypatch.setattr(claude_cli, "cli_version", lambda: "claude 9.9.9")

    sessions = [
        _session("flyer", ["search_flights"]),
        _session("quiet", []),
    ]
    db_rows = {"bookings": [], "trips": []}
    grades = [asyncio.run(grader.grade(s, db_rows)) for s in sessions]

    assert {g.persona_id: g.verdict for g in grades} == {
        "flyer": "fail",
        "quiet": "pass",
    }

    batch = BatchResult(sessions=sessions, status="ok", claude_calls=7)
    run_dir = tmp_path / "20260101T000000Z-abc123"
    grader.write_reports(run_dir, batch, grades, cli_version="claude 9.9.9")

    store = JsonDatasetStore(run_dir / "candidates", TAXONOMY)
    goldens = store.load()
    assert len(goldens) == 1
    candidate = goldens[0]
    assert candidate.capability == "flight_search"
    assert candidate.scenario == "multi_turn"
    assert candidate.suite == "full"
    assert candidate.turns == ["flyer asks for a flight"]
    assert candidate.id == "sim-20260101T000000Z-abc123-flyer"

    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["claude_calls"] == 7
    assert report["usage"] == {"total_tokens": 20}
    assert report["cli_version"] == "claude 9.9.9"

    lines = (run_dir / "report.md").read_text(encoding="utf-8").splitlines()
    fail_idx = next(i for i, ln in enumerate(lines) if "flyer" in ln)
    pass_idx = next(i for i, ln in enumerate(lines) if "quiet" in ln)
    assert fail_idx < pass_idx


def test_bot_error_session_maps_to_tool_failure_and_errors(tmp_path, monkeypatch):
    async def run(system_prompt, user_prompt, schema, model=None, timeout=120):
        return {
            "verdict": "warn",
            "score": 2.0,
            "summary": "s",
            "criteria": {c: {"score": 2.0, "evidence": "q"} for c in grader._CRITERIA},
        }

    monkeypatch.setattr(claude_cli, "run", run)
    monkeypatch.setattr(claude_cli, "cli_version", lambda: "claude 1.0")

    session = _session("erro", [], status="bot_error")
    grade = asyncio.run(grader.grade(session, {"bookings": [], "trips": []}))
    batch = BatchResult(sessions=[session], status="ok", claude_calls=1)
    run_dir = tmp_path / "ts-1"
    grader.write_reports(run_dir, batch, [grade])

    goldens = JsonDatasetStore(run_dir / "candidates", TAXONOMY).load()
    assert len(goldens) == 1
    assert goldens[0].capability == "errors"
    assert goldens[0].scenario == "tool_failure"


def test_grade_degrades_on_quota_exhausted(monkeypatch):
    async def run(system_prompt, user_prompt, schema, model=None, timeout=120):
        raise claude_cli.QuotaExhausted("no quota")

    monkeypatch.setattr(claude_cli, "run", run)
    grade = asyncio.run(grader.grade(_session("q", []), {"bookings": [], "trips": []}))
    assert grade.verdict == "fail"
    assert grade.score == 0.0
    assert grade.graded is False
    assert "quota" in grade.summary


def test_grade_degrades_on_driver_error(monkeypatch):
    async def run(system_prompt, user_prompt, schema, model=None, timeout=120):
        raise claude_cli.DriverError("boom")

    monkeypatch.setattr(claude_cli, "run", run)
    grade = asyncio.run(grader.grade(_session("d", []), {"bookings": [], "trips": []}))
    assert grade.verdict == "fail"
    assert grade.score == 0.0
    assert grade.graded is False
    assert "ungraded" in grade.summary


@pytest.mark.parametrize(
    ("tools", "status", "expected"),
    [
        (["search_flights"], "done", "flight_search"),
        (["search_hotels"], "done", "hotels"),
        (["search_hotels", "book_hotel"], "done", "booking"),
        (["book_flight"], "done", "booking"),
        (["estimate_trip_budget"], "done", "budget"),
        (["mystery_tool"], "done", "routing"),
        ([], "bot_error", "errors"),
        ([], "done", "routing"),
    ],
)
def test_capability_mapping(tools, status, expected):
    assert grader._capability(_session("c", tools, status=status)) == expected


def test_report_md_orders_fail_warn_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_cli, "cli_version", lambda: "claude 1.0")
    sessions = [
        _session("winner", []),
        _session("loser", ["search_flights"]),
        _session("meh", []),
    ]
    grades = [
        grader.Grade("winner", "pass", 5.0),
        grader.Grade("loser", "fail", 0.0),
        grader.Grade("meh", "warn", 2.0),
    ]
    batch = BatchResult(sessions=sessions, status="ok", claude_calls=3)
    run_dir = tmp_path / "ts-order"
    grader.write_reports(run_dir, batch, grades)

    lines = (run_dir / "report.md").read_text(encoding="utf-8").splitlines()
    fail_idx = next(i for i, ln in enumerate(lines) if "loser" in ln)
    warn_idx = next(i for i, ln in enumerate(lines) if "meh" in ln)
    pass_idx = next(i for i, ln in enumerate(lines) if "winner" in ln)
    assert fail_idx < warn_idx < pass_idx


def test_candidates_skip_sessions_without_user_turns(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_cli, "cli_version", lambda: "claude 1.0")
    empty = SessionResult(
        persona=_persona("silent"),
        conversation_id=None,
        status="quota",
        turns=[],
        tools=[],
    )
    batch = BatchResult(sessions=[empty], status="quota", claude_calls=0)
    run_dir = tmp_path / "ts-empty"
    grader.write_reports(run_dir, batch, [grader.Grade("silent", "fail", 0.0)])
    goldens = JsonDatasetStore(run_dir / "candidates", TAXONOMY).load()
    assert goldens == []


def test_ungraded_excluded_from_candidates_but_listed_first(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_cli, "cli_version", lambda: "claude 1.0")
    sessions = [
        _session("ok", ["search_flights"]),
        _session("broken", ["search_flights"]),
    ]
    grades = [
        grader.Grade("ok", "fail", 1.0),
        grader.Grade(
            "broken", "fail", 0.0, summary="ungraded: quota exhausted", graded=False
        ),
    ]
    batch = BatchResult(sessions=sessions, status="ok", claude_calls=2)
    run_dir = tmp_path / "ts-ungraded"
    grader.write_reports(run_dir, batch, grades)

    goldens = JsonDatasetStore(run_dir / "candidates", TAXONOMY).load()
    assert [g.id for g in goldens] == ["sim-ts-ungraded-ok"]

    lines = (run_dir / "report.md").read_text(encoding="utf-8").splitlines()
    broken_line = next(ln for ln in lines if "broken" in ln)
    assert "ungraded" in broken_line
    broken_idx = next(i for i, ln in enumerate(lines) if "broken" in ln)
    ok_idx = next(i for i, ln in enumerate(lines) if "| ok " in ln)
    assert broken_idx < ok_idx


def _fake_run_returning(payload):
    async def run(system_prompt, user_prompt, schema, model=None, timeout=120):
        return payload

    return run


def test_grade_coerces_null_score_to_zero(monkeypatch):
    monkeypatch.setattr(
        claude_cli, "run", _fake_run_returning({"verdict": "pass", "score": None})
    )
    grade = asyncio.run(grader.grade(_session("n", []), {"bookings": [], "trips": []}))
    assert grade.graded is True
    assert grade.verdict == "pass"
    assert grade.score == 0.0


def test_grade_coerces_non_numeric_and_clamps_score(monkeypatch):
    monkeypatch.setattr(
        claude_cli, "run", _fake_run_returning({"verdict": "pass", "score": "8/10"})
    )
    bad = asyncio.run(grader.grade(_session("s1", []), {"bookings": [], "trips": []}))
    assert bad.score == 0.0

    monkeypatch.setattr(
        claude_cli, "run", _fake_run_returning({"verdict": "pass", "score": 9.0})
    )
    high = asyncio.run(grader.grade(_session("s2", []), {"bookings": [], "trips": []}))
    assert high.score == 5.0


def test_grade_survives_arbitrary_grader_crash(monkeypatch):
    async def run(system_prompt, user_prompt, schema, model=None, timeout=120):
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(claude_cli, "run", run)
    grade = asyncio.run(grader.grade(_session("c", []), {"bookings": [], "trips": []}))
    assert grade.graded is False
    assert grade.verdict == "fail"
    assert grade.score == 0.0
    assert "grader error" in grade.summary


def test_report_json_verdict_is_ungraded_when_not_graded(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_cli, "cli_version", lambda: "claude 1.0")
    session = _session("u", ["search_flights"])
    grades = [
        grader.Grade("u", "fail", 0.0, summary="ungraded: grader error", graded=False)
    ]
    batch = BatchResult(sessions=[session], status="ok", claude_calls=1)
    run_dir = tmp_path / "ts-verdict"
    grader.write_reports(run_dir, batch, grades)
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["sessions"][0]["verdict"] == "ungraded"
    assert report["sessions"][0]["graded"] is False


def _resume_session(pid, approved):
    return SessionResult(
        persona=_persona(pid),
        conversation_id=f"conv-{pid}",
        status="done",
        turns=[
            {"role": "user", "text": f"{pid} wants to book"},
            {"role": "bot", "text": "Approve?"},
            {"role": "user", "text": f"[resume approved={approved}]"},
            {"role": "bot", "text": "Booked"},
        ],
        tools=["book_flight"],
        panels=[],
        usage={},
    )


def test_candidate_full_suite_marker_excluded_and_hitl_set(tmp_path):
    session = _resume_session("booker", True)
    grade = grader.Grade("booker", "fail", 1.0)
    batch = BatchResult(sessions=[session], status="ok", claude_calls=1)
    run_dir = tmp_path / "20260101T000000Z-hit"
    grader.write_reports(run_dir, batch, [grade])

    goldens = JsonDatasetStore(run_dir / "candidates", TAXONOMY).load(suite="full")
    assert len(goldens) == 1
    candidate = goldens[0]
    assert candidate.suite == "full"
    assert candidate.hitl == "approve"
    assert candidate.capability == "booking"
    assert candidate.turns == ["booker wants to book"]
    assert all("resume approved" not in t for t in candidate.turns)


def test_candidate_hitl_reject_when_resume_declined(tmp_path):
    session = _resume_session("decliner", False)
    grade = grader.Grade("decliner", "warn", 2.0)
    batch = BatchResult(sessions=[session], status="ok", claude_calls=1)
    run_dir = tmp_path / "20260101T000000Z-rej"
    grader.write_reports(run_dir, batch, [grade])
    goldens = JsonDatasetStore(run_dir / "candidates", TAXONOMY).load()
    assert goldens[0].hitl == "reject"


def test_coerce_score_maps_nan_to_zero():
    assert grader._coerce_score(float("nan")) == 0.0


def test_marker_only_session_is_not_a_candidate():
    session = _session("p9", ["search_flights"])
    session.turns = [{"role": "user", "text": "[resume approved=True]"}]
    assert not grader._has_user_turn(session)
