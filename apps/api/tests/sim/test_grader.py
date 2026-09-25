"""Grader + reports tests (offline: fake claude_cli.run, fixture SessionResults)."""

from __future__ import annotations

import asyncio
import json

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
    grader.write_reports(run_dir, batch, grades)

    store = JsonDatasetStore(run_dir / "candidates", TAXONOMY)
    goldens = store.load()
    assert len(goldens) == 1
    candidate = goldens[0]
    assert candidate.capability == "flight_search"
    assert candidate.scenario == "multi_turn"
    assert candidate.suite == "sim"
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
