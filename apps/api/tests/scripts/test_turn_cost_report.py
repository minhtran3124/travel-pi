"""CLI cost-per-turn report (#350), on seeded SQLite data; no LLM calls."""

from types import SimpleNamespace

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run import AgentRun


def _run(id, user, day, flow, cost, tin=100, tout=50):
    return AgentRun(
        id=id,
        user_id=user,
        conversation_id="c1",
        thread_id="t1",
        channel="web",
        kind="chat",
        status="succeeded",
        created_at=f"{day}T12:00:00+00:00",
        current_flow=flow,
        input_tokens=tin,
        output_tokens=tout,
        cost_usd=cost,
        by_model={"gpt-5": {"calls": 1}},
    )


def _seed():
    return [
        _run("a", "u1", "2026-08-10", "planner", 0.10),
        _run("b", "u1", "2026-08-10", "planner", 0.30),
        _run("c", "u1", "2026-08-11", "budget", 0.20),
        _run("d", "u2", "2026-08-10", "planner", 0.40),
        _run("e", "u2", "2026-08-10", "budget", None),  # unpriced
    ]


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'turn.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    with factory() as s:
        s.add_all(_seed())
        s.commit()
    settings = SimpleNamespace(database_url=url, agent_free_daily_turn_limit=20)
    import scripts.turn_cost_report as mod

    monkeypatch.setattr(mod, "get_settings", lambda: settings)
    return url


def _rows(url):
    from datetime import datetime, timedelta, timezone

    from app.repositories.agent_run import AgentRunRepository

    since = datetime.now(timezone.utc) - timedelta(days=3650)
    return AgentRunRepository(get_session_factory(url)).turn_cost_rows_since(since)


def test_build_report_averages_and_unpriced(db_url):
    from scripts.turn_cost_report import build_report

    r = build_report(_rows(db_url), 20)
    assert r["priced_turns"] == 4
    assert r["unpriced_turns"] == 1
    assert r["total_cost_usd"] == pytest.approx(1.0)
    assert r["avg_cost_per_turn"] == pytest.approx(0.25)
    assert r["active_users"] == 2
    # user-days: u1/10th=0.40, u1/11th=0.20, u2/10th=0.40
    assert r["avg_cost_per_user_day"] == pytest.approx(1.0 / 3)
    assert r["max_cost_per_user_day"] == pytest.approx(0.40)


def test_build_report_capability_split(db_url):
    from scripts.turn_cost_report import build_report

    caps = {c["capability"]: c for c in build_report(_rows(db_url))["capabilities"]}
    assert caps["planner"]["turns"] == 3
    assert caps["planner"]["cost_usd"] == pytest.approx(0.8)
    assert caps["budget"]["turns"] == 1
    assert caps["budget"]["avg_cost_per_turn"] == pytest.approx(0.2)


def test_build_report_projection_and_free_tier(db_url):
    from scripts.turn_cost_report import build_report

    r = build_report(_rows(db_url), 20)
    assert r["projected_monthly_cost_per_user"] == pytest.approx(10.0)
    assert r["free_tier"]["max_cost_per_user_day_usd"] == pytest.approx(5.0)
    assert r["free_tier"]["max_cost_per_user_month_usd"] == pytest.approx(150.0)


def test_zero_token_null_cost_is_not_unpriced():
    from scripts.turn_cost_report import build_report

    row = SimpleNamespace(
        user_id="u",
        current_flow=None,
        created_at="2026-08-01T00:00:00",
        cost_usd=None,
        input_tokens=0,
        output_tokens=0,
        by_model={},
    )
    r = build_report([row])
    assert r["unpriced_turns"] == 0
    assert r["priced_turns"] == 0
    assert r["avg_cost_per_turn"] == 0.0


def test_main_prints_and_exits_zero(db_url, capsys):
    from scripts.turn_cost_report import main

    assert main(["--since", "3650d"]) == 0
    out = capsys.readouterr().out
    assert "avg cost per turn" in out
    assert "planner" in out
    assert "agent_free_daily_turn_limit=20" in out


def test_main_empty_window_exits_three(db_url, capsys):
    from scripts.turn_cost_report import main

    assert main(["--since", "1d"]) == 3
    assert "no agent runs" in capsys.readouterr().out


def test_main_invalid_since_exits_two(capsys):
    from scripts.turn_cost_report import main

    with pytest.raises(SystemExit) as exc:
        main(["--since", "bogus"])
    assert exc.value.code == 2
