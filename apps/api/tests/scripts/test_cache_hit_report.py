"""CLI cache hit-rate report (specs/prompt-caching-system-prefix Task 1.2)."""

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run_step import AgentRunStep


def _step(*, node, model, kind, input_tokens, cached_tokens, seq):
    return AgentRunStep(
        run_id="r1",
        seq=seq,
        kind=kind,
        node=node,
        model=model,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        status="ok",
    )


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'cache.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(get_engine(url), checkfirst=True)

    rows = [
        _step(
            node="supervisor",
            model="gpt-5",
            kind="llm",
            input_tokens=3000,
            cached_tokens=2816,
            seq=0,
        ),
        _step(
            node="supervisor",
            model="gpt-5",
            kind="llm",
            input_tokens=3000,
            cached_tokens=0,
            seq=1,
        ),
        _step(
            node="supervisor",
            model="gpt-5",
            kind="tool",
            input_tokens=999,
            cached_tokens=0,
            seq=2,
        ),
        _step(
            node="assistant",
            model="gpt-5",
            kind="llm",
            input_tokens=3000,
            cached_tokens=2816,
            seq=3,
        ),
    ]
    with factory() as s:
        s.add_all(rows)
        s.commit()

    # cache_hit_report reads get_settings().database_url — point it at the temp db.
    from app.core import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "database_url", url, raising=False)
    config.get_settings.cache_clear()
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    import scripts.cache_hit_report as mod

    monkeypatch.setattr(mod, "get_settings", lambda: settings)
    return url


def test_build_report_aggregates_per_node_and_model():
    from scripts.cache_hit_report import build_report

    rows = [
        _step(
            node="supervisor",
            model="gpt-5",
            kind="llm",
            input_tokens=3000,
            cached_tokens=2816,
            seq=0,
        ),
        _step(
            node="supervisor",
            model="gpt-5",
            kind="llm",
            input_tokens=3000,
            cached_tokens=0,
            seq=1,
        ),
        _step(
            node="assistant",
            model="gpt-5",
            kind="llm",
            input_tokens=3000,
            cached_tokens=2816,
            seq=2,
        ),
    ]
    report = build_report(rows)

    by_key = {(r["node"], r["model"]): r for r in report["rows"]}
    sup = by_key[("supervisor", "gpt-5")]
    assert sup["calls"] == 2
    assert sup["input"] == 6000
    assert sup["cached"] == 2816
    # uncached is a TOKEN delta; miss_calls is a COUNT of zero-cache calls.
    assert sup["uncached"] == 3184
    assert sup["miss_calls"] == 1
    assert sup["ratio"] == pytest.approx(2816 / 6000)

    asst = by_key[("assistant", "gpt-5")]
    assert asst["calls"] == 1
    assert asst["input"] == 3000
    assert asst["cached"] == 2816
    assert asst["uncached"] == 184
    assert asst["miss_calls"] == 0
    assert asst["ratio"] == pytest.approx(2816 / 3000)

    assert report["overall"] == pytest.approx(5632 / 9000)


def test_build_report_zero_input_is_zero_ratio():
    from scripts.cache_hit_report import build_report

    report = build_report(
        [
            _step(
                node="reflection",
                model="gpt-5",
                kind="llm",
                input_tokens=0,
                cached_tokens=0,
                seq=0,
            )
        ]
    )
    assert report["rows"][0]["ratio"] == 0.0
    assert report["overall"] == 0.0


def test_main_gates_on_min_ratio(db_url):
    from scripts.cache_hit_report import main

    # overall ratio is 5632/9000 ~= 0.626 (tool step excluded).
    assert main(["--since", "1d", "--min-ratio", "0.9"]) == 1
    assert main(["--since", "1d", "--min-ratio", "0.4"]) == 0


def test_main_without_min_ratio_exits_zero(db_url):
    from scripts.cache_hit_report import main

    assert main(["--since", "1d"]) == 0


def test_db_path_excludes_non_llm_steps(db_url):
    """The report reads through the repository, which filters kind == 'llm'.

    The fixture inserts a 999-input tool step; it must not reach the report,
    so total input is 9000 (three llm steps) not 9999, and no row exists for
    the tool step's (node, model) key beyond the llm rows.
    """
    from datetime import datetime, timedelta, timezone

    from app.core.config import get_settings
    from app.db.engine import get_session_factory
    from app.repositories.agent_run import AgentRunRepository
    from scripts.cache_hit_report import build_report

    since = datetime.now(timezone.utc) - timedelta(days=1)
    factory = get_session_factory(get_settings().database_url)
    rows = AgentRunRepository(factory).llm_steps_since(since)

    # Only the three llm steps come back; the tool step is filtered out.
    assert all(r.kind == "llm" for r in rows)
    report = build_report(rows)
    total_input = sum(r["input"] for r in report["rows"])
    assert total_input == 9000
    assert not any(r["input"] == 999 for r in report["rows"])
    assert report["overall"] == pytest.approx(5632 / 9000)


def test_main_node_filter_narrows_rows_and_ratio(db_url, capsys):
    from scripts.cache_hit_report import main

    # --node supervisor keeps only the two supervisor llm steps: 2816/6000.
    out = main(["--since", "1d", "--node", "supervisor"])
    assert out == 0
    printed = capsys.readouterr().out
    assert "supervisor" in printed
    assert "assistant" not in printed

    # The narrowed overall ratio (0.469) gates between 0.4 and 0.5; if the
    # assistant rows leaked in, the overall would be 0.626 and pass 0.5.
    assert main(["--since", "1d", "--node", "supervisor", "--min-ratio", "0.4"]) == 0
    assert main(["--since", "1d", "--node", "supervisor", "--min-ratio", "0.5"]) == 1


def test_parse_since_raises_on_invalid_value():
    from scripts.cache_hit_report import _parse_since

    with pytest.raises(ValueError):
        _parse_since("bogus")


def test_main_invalid_since_is_argparse_error(capsys):
    from scripts.cache_hit_report import main

    with pytest.raises(SystemExit) as exc:
        main(["--since", "bogus"])
    # argparse usage error exits 2, not an unhandled ValueError traceback.
    assert exc.value.code == 2
    assert "--since" in capsys.readouterr().err


def test_main_no_rows_with_min_ratio_exits_three(db_url, capsys):
    """No matching llm steps + --min-ratio: exit 3 (no data), not 1 (regressed).

    A gate must tell "nothing was measured" apart from "the cache regressed",
    so an empty window fails closed with a distinct code and never prints a
    0.0% hit rate as if it were a measurement.
    """
    from scripts.cache_hit_report import main

    code = main(["--since", "1d", "--node", "does-not-exist", "--min-ratio", "0.1"])
    assert code == 3
    printed = capsys.readouterr().out
    assert "0.0%" not in printed
    assert "does-not-exist" in printed
    assert "1d" in printed
    # A clear no-data message, not a hit-rate line.
    assert "no LLM steps" in printed


def test_main_no_rows_without_min_ratio_exits_zero(db_url, capsys):
    """No matching llm steps + no --min-ratio: a plain empty window is exit 0."""
    from scripts.cache_hit_report import main

    code = main(["--since", "1d", "--node", "does-not-exist"])
    assert code == 0
    printed = capsys.readouterr().out
    assert "0.0%" not in printed
    assert "no LLM steps" in printed
    assert "does-not-exist" in printed


def test_main_rows_with_zero_input_is_no_data(db_url, capsys):
    """Rows that carry no input tokens are "nothing measurable", not a 0% hit rate.

    A window can match llm steps that recorded 0 input tokens — a step closed by
    an LLM error or swept as unfinished. Gating that as "0.0% below --min-ratio"
    reports a regression when nothing was measured; it must exit 3 like an empty
    window, and never print a 0.0% rate.
    """
    from scripts.cache_hit_report import main

    factory = get_session_factory(db_url)
    with factory() as s:
        s.add(
            _step(
                node="reflection",
                model="gpt-5",
                kind="llm",
                input_tokens=0,
                cached_tokens=0,
                seq=10,
            )
        )
        s.commit()

    code = main(["--since", "1d", "--node", "reflection", "--min-ratio", "0.1"])
    assert code == 3
    printed = capsys.readouterr().out
    assert "0.0%" not in printed
    assert "nothing to measure" in printed
