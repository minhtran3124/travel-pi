"""CLI monthly cost-coverage report (specs/llm-pricing-coverage Task 1.2)."""

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run import AgentRun


def _run(
    *,
    id,
    created_at,
    cost_usd,
    input_tokens,
    output_tokens,
    by_model,
    background_tokens,
):
    return AgentRun(
        id=id,
        user_id="u1",
        conversation_id="c1",
        thread_id="t1",
        channel="web",
        kind="chat",
        status="succeeded",
        created_at=created_at,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        by_model=by_model,
        background_tokens=background_tokens,
    )


def _seed_rows():
    # Two August runs (one priced, one unpriced) and one September run, so the
    # report must split by month and count the NULL-cost run as unpriced.
    return [
        _run(
            id="a",
            created_at="2026-08-10T12:00:00+00:00",
            cost_usd=1.5,
            input_tokens=100,
            output_tokens=50,
            by_model={"gpt-5": {"calls": 1}},
            background_tokens=10,
        ),
        _run(
            id="b",
            created_at="2026-08-20T12:00:00+00:00",
            cost_usd=None,
            input_tokens=200,
            output_tokens=100,
            by_model={"mystery-model": {"calls": 1}},
            background_tokens=5,
        ),
        _run(
            id="c",
            created_at="2026-09-05T12:00:00+00:00",
            cost_usd=2.0,
            input_tokens=300,
            output_tokens=100,
            by_model={"gpt-5": {"calls": 1}},
            background_tokens=0,
        ),
    ]


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'cost.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    with factory() as s:
        s.add_all(_seed_rows())
        s.commit()

    # cost_report reads get_settings().database_url — point it at the temp db.
    from app.core import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "database_url", url, raising=False)
    config.get_settings.cache_clear()
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    import scripts.cost_report as mod

    monkeypatch.setattr(mod, "get_settings", lambda: settings)
    return url


def _rows_since(url, days):
    from datetime import datetime, timedelta, timezone

    from app.repositories.agent_run import AgentRunRepository

    since = datetime.now(timezone.utc) - timedelta(days=days)
    return AgentRunRepository(get_session_factory(url)).cost_rows_since(since)


def test_build_report_groups_by_month(db_url):
    from scripts.cost_report import build_report

    report = build_report(_rows_since(db_url, 3650))
    by_month = {m["month"]: m for m in report["months"]}

    assert set(by_month) == {"2026-08", "2026-09"}

    aug = by_month["2026-08"]
    assert aug["runs"] == 2
    assert aug["priced_cost_usd"] == pytest.approx(1.5)
    # The NULL-cost August run is unpriced, with its model listed.
    assert aug["unpriced_runs"] == 1
    assert aug["unpriced_tokens"] == 300
    assert aug["unpriced_models"] == ["mystery-model"]
    assert aug["background_tokens"] == 15

    sep = by_month["2026-09"]
    assert sep["runs"] == 1
    assert sep["priced_cost_usd"] == pytest.approx(2.0)
    assert sep["unpriced_runs"] == 0
    assert sep["unpriced_models"] == []


def test_main_prints_and_exits_zero(db_url, capsys):
    from scripts.cost_report import main

    assert main(["--since", "3650d"]) == 0
    printed = capsys.readouterr().out
    assert "2026-08" in printed
    assert "2026-09" in printed
    assert "mystery-model" in printed
    assert "invoice" in printed


def test_main_empty_window_exits_three(db_url, capsys):
    from scripts.cost_report import main

    # All seeded runs predate a 1-day window, so nothing matches.
    code = main(["--since", "1d"])
    assert code == 3
    printed = capsys.readouterr().out
    assert "no agent runs" in printed
    assert "1d" in printed


def test_main_invalid_since_is_argparse_error(capsys):
    from scripts.cost_report import main

    with pytest.raises(SystemExit) as exc:
        main(["--since", "bogus"])
    # argparse usage error exits 2, not an unhandled ValueError traceback.
    assert exc.value.code == 2
    assert "--since" in capsys.readouterr().err


def test_build_report_zero_token_null_cost_run_is_not_unpriced():
    from types import SimpleNamespace

    from scripts.cost_report import build_report

    row = SimpleNamespace(
        created_at="2026-09-02T00:00:00",
        input_tokens=0,
        output_tokens=0,
        cost_usd=None,
        by_model={},
        background_tokens=0,
    )
    (month,) = build_report([row])["months"]
    assert month["runs"] == 1
    assert month["unpriced_runs"] == 0
    assert month["priced_cost_usd"] == 0.0


def test_build_report_lists_only_the_unpriced_models_of_a_mixed_run():
    from types import SimpleNamespace

    from scripts.cost_report import build_report

    row = SimpleNamespace(
        created_at="2026-09-02T00:00:00",
        input_tokens=100,
        output_tokens=50,
        cost_usd=None,
        by_model={"gpt-5-2026-01-15": {}, "mystery-model": {}},
        background_tokens=0,
    )
    (month,) = build_report([row])["months"]
    assert month["unpriced_models"] == ["mystery-model"]


def test_main_huge_since_is_argparse_error(capsys):
    from scripts.cost_report import main

    with pytest.raises(SystemExit) as exc:
        main(["--since", "100000000000d"])
    assert exc.value.code == 2


def test_print_table_marks_only_the_partial_first_month(capsys):
    from datetime import datetime, timezone

    from scripts.cost_report import _print_table

    report = {
        "months": [
            {
                "month": month,
                "runs": 1,
                "priced_cost_usd": 1.0,
                "unpriced_runs": 0,
                "unpriced_tokens": 0,
                "unpriced_models": [],
                "background_tokens": 0,
            }
            for month in ("2026-08", "2026-09")
        ]
    }
    _print_table(report, datetime(2026, 8, 26, tzinfo=timezone.utc))
    out = capsys.readouterr().out
    assert "2026-08*" in out
    assert "2026-09*" not in out
    assert "partial month" in out
