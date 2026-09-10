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
        _step(node="supervisor", model="gpt-5", kind="llm",
              input_tokens=3000, cached_tokens=2816, seq=0),
        _step(node="supervisor", model="gpt-5", kind="llm",
              input_tokens=3000, cached_tokens=0, seq=1),
        _step(node="supervisor", model="gpt-5", kind="tool",
              input_tokens=999, cached_tokens=0, seq=2),
        _step(node="assistant", model="gpt-5", kind="llm",
              input_tokens=3000, cached_tokens=2816, seq=3),
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
        _step(node="supervisor", model="gpt-5", kind="llm",
              input_tokens=3000, cached_tokens=2816, seq=0),
        _step(node="supervisor", model="gpt-5", kind="llm",
              input_tokens=3000, cached_tokens=0, seq=1),
        _step(node="assistant", model="gpt-5", kind="llm",
              input_tokens=3000, cached_tokens=2816, seq=2),
    ]
    report = build_report(rows)

    by_key = {(r["node"], r["model"]): r for r in report["rows"]}
    sup = by_key[("supervisor", "gpt-5")]
    assert sup["calls"] == 2
    assert sup["input"] == 6000
    assert sup["cached"] == 2816
    assert sup["misses"] == 3184
    assert sup["ratio"] == pytest.approx(2816 / 6000)

    asst = by_key[("assistant", "gpt-5")]
    assert asst["calls"] == 1
    assert asst["input"] == 3000
    assert asst["cached"] == 2816
    assert asst["misses"] == 184
    assert asst["ratio"] == pytest.approx(2816 / 3000)

    assert report["overall"] == pytest.approx(5632 / 9000)


def test_build_report_zero_input_is_zero_ratio():
    from scripts.cache_hit_report import build_report

    report = build_report(
        [_step(node="reflection", model="gpt-5", kind="llm",
               input_tokens=0, cached_tokens=0, seq=0)]
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
