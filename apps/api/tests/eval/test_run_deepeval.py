"""Offline tests for the keyed DeepEval runner (MIN-58).

All tests are no-network: the skip-path tests never build a graph or judge, and
``build_test_cases`` is driven by a local stub graph so no metric/GEval object is
ever constructed (which would eagerly require a real OPENAI_API_KEY).
"""

import eval.run_deepeval as r


def test_skips_without_real_key(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert r.main() == 0
    assert "SKIP" in capsys.readouterr().out


def test_skips_when_key_absent(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert r.main() == 0
    assert "SKIP" in capsys.readouterr().out


def test_has_real_openai_key_detection(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-realish")
    assert r.has_real_openai_key() is True
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert r.has_real_openai_key() is False


class _StubGraph:
    """Minimal graph stand-in: .invoke returns a canned result (no network, no cross-test import)."""

    def invoke(self, state, cfg, context=None):
        from langchain_core.messages import AIMessage

        return {"messages": [AIMessage(content="ok")], "current_flow": "concierge"}


def test_build_test_cases_fans_dataset_through_harness():
    cases = r.build_test_cases(_StubGraph(), {"d": [{"input": "a"}, {"input": "b"}]})
    assert len(cases) == 2
    assert [c.input for c in cases] == ["a", "b"]
