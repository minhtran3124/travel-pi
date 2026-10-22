"""SC-8 — the CLI preflight (design §7).

Each case must exit 2 before any ``claude`` process is spawned, so the fake
``claude`` records zero calls. The tests are synchronous: ``main`` returns the
exit code and every preflight failure returns before the batch runs.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from sim.__main__ import main

FAKE = Path(__file__).parent / "fixtures" / "fake_claude.py"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def env_file(tmp_path) -> Path:
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    return path


@pytest.fixture()
def calls_file(monkeypatch, tmp_path) -> Path:
    path = tmp_path / "calls.txt"
    monkeypatch.setenv("FAKE_CLAUDE_CALLS_FILE", str(path))
    monkeypatch.setenv("SIM_CLAUDE_BIN", str(FAKE))
    return path


def _assert_no_claude_call(calls_file: Path) -> None:
    if not calls_file.exists():
        return
    lines = [ln for ln in calls_file.read_text().splitlines() if ln]
    assert lines == []


def test_missing_claude_binary_exits_two(calls_file, env_file, monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_CLAUDE_BIN", str(tmp_path / "no-such-claude"))
    code = main(
        [
            "--base-url",
            "http://localhost:8001",
            "--env-file",
            str(env_file),
        ]
    )
    assert code == 2
    _assert_no_claude_call(calls_file)


def test_wrong_port_without_i_know_exits_two(calls_file, env_file):
    code = main(
        [
            "--base-url",
            "http://localhost:8000",
            "--env-file",
            str(env_file),
        ]
    )
    assert code == 2
    _assert_no_claude_call(calls_file)


def test_empty_openai_key_exits_two(calls_file, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=\n", encoding="utf-8")
    code = main(
        [
            "--base-url",
            "http://localhost:8001",
            "--env-file",
            str(env_file),
        ]
    )
    assert code == 2
    _assert_no_claude_call(calls_file)


def test_healthz_unreachable_exits_two(calls_file, env_file):
    port = _free_port()
    code = main(
        [
            "--base-url",
            f"http://localhost:{port}",
            "--i-know",
            "--env-file",
            str(env_file),
        ]
    )
    assert code == 2
    _assert_no_claude_call(calls_file)


def test_client_read_timeout_covers_a_full_turn():
    from sim import driver
    from sim.__main__ import _client_timeout

    timeout = _client_timeout()
    assert timeout.read >= driver.TURN_TIMEOUT
    assert timeout.connect >= 10.0


class _CollectingBus:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event) -> None:
        self.events.append(event)


def _one_session_batch():
    from datetime import datetime, timezone

    from sim.driver import BatchResult, SessionResult
    from sim.personas import Budget, Persona, TripGoal

    persona = Persona(
        id="p1",
        name="Ana",
        country_code="US",
        language="en",
        budget=Budget(amount=1000, currency="USD"),
        trip_goal=TripGoal(destination="Rome", party_size=1),
        style="terse",
        will_book=False,
        max_turns=4,
    )
    session = SessionResult(
        persona=persona,
        conversation_id="c1",
        status="done",
        turns=[{"role": "user", "text": "hi"}],
        started_at=datetime.now(timezone.utc),
    )
    return BatchResult(sessions=[session], status="ok", claude_calls=1)


@pytest.mark.asyncio
async def test_snapshot_failure_still_writes_reports(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    from sim import __main__ as cli
    from sim.grader import Grade

    def _raise(*args, **kwargs):
        raise RuntimeError("db-sim is down")

    async def _fake_grade(session, rows):
        assert rows == {"bookings": [], "trips": []}
        return Grade(persona_id=session.persona.id, verdict="pass", score=5.0)

    monkeypatch.setattr(cli, "sim_session_factory", lambda url: object())
    monkeypatch.setattr(cli, "snapshot", _raise)
    monkeypatch.setattr(cli, "grade", _fake_grade)

    batch = _one_session_batch()
    grades = await cli._grade_all(batch, _CollectingBus(), datetime.now(timezone.utc))
    cli.write_reports(tmp_path, batch, grades)

    assert (tmp_path / "report.json").is_file()
    assert (tmp_path / "report.md").is_file()


def test_run_failure_returns_three(calls_file, env_file, monkeypatch):
    from sim import __main__ as cli

    def _boom(args):
        raise RuntimeError("the batch blew up")

    # Preflight passes (fake claude on PATH, valid env), and healthz is stubbed
    # so the failure comes from _run, not the network probe.
    monkeypatch.setattr(cli, "_healthz_ok", lambda base_url: True)
    monkeypatch.setattr(cli, "_run", _boom)
    code = cli.main(
        [
            "--base-url",
            "http://localhost:8001",
            "--env-file",
            str(env_file),
        ]
    )
    assert code == 3
    _assert_no_claude_call(calls_file)


@pytest.mark.parametrize("parallel", ["7", "0", "-1"])
def test_parallel_out_of_range_exits_two(calls_file, env_file, parallel):
    code = main(
        [
            "--base-url",
            "http://localhost:8001",
            "--env-file",
            str(env_file),
            "--parallel",
            parallel,
        ]
    )
    assert code == 2
    _assert_no_claude_call(calls_file)


def _session_with_turns(pid, turns):
    from sim.driver import SessionResult
    from sim.personas import Budget, Persona, TripGoal

    persona = Persona(
        id=pid,
        name=pid,
        language="en",
        budget=Budget(amount=1000, currency="USD"),
        trip_goal=TripGoal(destination="Rome", party_size=1),
        style="terse",
        will_book=False,
        max_turns=4,
    )
    return SessionResult(
        persona=persona,
        conversation_id=None,
        status="done",
        turns=turns,
    )


@pytest.mark.asyncio
async def test_grade_all_skips_sessions_that_never_ran(monkeypatch):
    from datetime import datetime, timezone

    from sim import __main__ as cli
    from sim import claude_cli
    from sim.driver import BatchResult
    from sim.grader import Grade

    monkeypatch.setattr(cli, "sim_session_factory", lambda url: None)
    claude_cli.last_quota = None
    calls = []

    async def _fake_grade(session, rows):
        calls.append(session.persona.id)
        return Grade(persona_id=session.persona.id, verdict="pass", score=5.0)

    monkeypatch.setattr(cli, "grade", _fake_grade)

    ran = _session_with_turns("ran", [{"role": "user", "text": "hi"}])
    never = _session_with_turns("never", [])
    batch = BatchResult(sessions=[never, ran], status="quota", claude_calls=0)

    grades = await cli._grade_all(batch, _CollectingBus(), datetime.now(timezone.utc))
    by_id = {g.persona_id: g for g in grades}
    assert calls == ["ran"]
    assert by_id["never"].graded is False
    assert "never ran" in by_id["never"].summary
    assert by_id["ran"].graded is True


@pytest.mark.asyncio
async def test_grade_all_stops_grading_over_quota_ceiling(monkeypatch):
    from datetime import datetime, timezone

    from sim import __main__ as cli
    from sim import claude_cli
    from sim.driver import DEFAULT_CEILING, BatchResult
    from sim.grader import Grade

    monkeypatch.setenv("SIM_QUOTA_CEILING", str(DEFAULT_CEILING))
    monkeypatch.setattr(cli, "sim_session_factory", lambda url: None)
    claude_cli.last_quota = claude_cli.Quota(
        five_hour=0.99, seven_day=0.1, resets_at=None
    )
    calls = []

    async def _fake_grade(session, rows):
        calls.append(session.persona.id)
        return Grade(persona_id=session.persona.id, verdict="pass", score=5.0)

    monkeypatch.setattr(cli, "grade", _fake_grade)

    a = _session_with_turns("a", [{"role": "user", "text": "hi"}])
    b = _session_with_turns("b", [{"role": "user", "text": "yo"}])
    batch = BatchResult(sessions=[a, b], status="ok", claude_calls=0)

    grades = await cli._grade_all(batch, _CollectingBus(), datetime.now(timezone.utc))
    claude_cli.last_quota = None
    assert calls == []
    assert all(not g.graded for g in grades)
    assert all("quota ceiling" in g.summary for g in grades)
