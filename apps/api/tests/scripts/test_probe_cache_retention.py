"""Two-phase A/B prompt-cache retention probe (specs/prompt-caching-system-prefix Task 2.2).

Offline: ``_build_chat_model`` is monkeypatched to a stub whose ``AIMessage``
carries ``usage_metadata.input_token_details.cache_read`` per retention arm, and
``time.time`` is controlled to drive the elapsed-gap logic. No network, no key.
"""

import json

import pytest
import scripts.probe_cache_retention as mod


class _StubMsg:
    def __init__(self, input_tokens: int, cache_read: int) -> None:
        self.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": 0,
            "total_tokens": input_tokens,
            "input_token_details": {"cache_read": cache_read},
        }


class _StubModel:
    """Records invoke calls; returns a configurable cache_read for its arm."""

    def __init__(self, cache_read: int, calls: list) -> None:
        self._cache_read = cache_read
        self._calls = calls

    def invoke(self, prompt):
        self._calls.append(prompt)
        return _StubMsg(input_tokens=3000, cache_read=self._cache_read)


def _make_build(cache_by_value: dict[str, int], calls: dict[str, list]):
    def _fake(provider, model, *, model_kwargs=None, **kw):
        value = (model_kwargs or {})["prompt_cache_retention"]
        calls.setdefault(value, [])
        return _StubModel(cache_by_value.get(value, 0), calls[value])

    return _fake


def _run(monkeypatch, argv: list[str]):
    monkeypatch.setattr("sys.argv", ["probe_cache_retention", *argv])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    return exc.value.code


def _write_state(path, seeded_at: float, model: str = "fake") -> None:
    path.write_text(
        json.dumps(
            {
                "model": model,
                "seeded_at": seeded_at,
                "arms": {
                    "24h": {"nonce": "nonce-24h"},
                    "in_memory": {"nonce": "nonce-ctl"},
                },
            }
        )
    )


def test_seed_writes_two_nonces_and_timestamp(monkeypatch, tmp_path):
    calls: dict[str, list] = {}
    monkeypatch.setattr(mod, "_build_chat_model", _make_build({}, calls))
    monkeypatch.setattr("time.time", lambda: 1000.0)
    state = tmp_path / "probe.json"

    code = _run(monkeypatch, ["--seed", "--state", str(state), "--model", "fake"])

    assert code == 0
    data = json.loads(state.read_text())
    assert data["seeded_at"] == 1000.0
    assert set(data["arms"]) == {"24h", "in_memory"}
    nonces = {arm["nonce"] for arm in data["arms"].values()}
    assert len(nonces) == 2  # each arm nonced separately
    # second call per arm is what proves the cache write landed
    assert len(calls["24h"]) == 2
    assert len(calls["in_memory"]) == 2


def test_check_exits_2_below_min_gap(monkeypatch, tmp_path):
    state = tmp_path / "probe.json"
    _write_state(state, seeded_at=1000.0)
    monkeypatch.setattr(mod, "_build_chat_model", _make_build({}, {}))
    monkeypatch.setattr("time.time", lambda: 1000.0 + 30 * 60)  # 30 min < 60

    code = _run(monkeypatch, ["--check", "--state", str(state)])

    assert code == 2


def _run_check_verdict(monkeypatch, tmp_path, cache_by_value):
    state = tmp_path / "probe.json"
    _write_state(state, seeded_at=1000.0)
    monkeypatch.setattr(mod, "_build_chat_model", _make_build(cache_by_value, {}))
    monkeypatch.setattr("time.time", lambda: 1000.0 + 61 * 60)  # 61 min >= 60
    return state


def test_check_retention_wins(monkeypatch, tmp_path, capsys):
    _run_check_verdict(monkeypatch, tmp_path, {"24h": 2900, "in_memory": 0})
    code = _run(monkeypatch, ["--check", "--state", str(tmp_path / "probe.json")])
    assert code == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "RETENTION-WINS"


def test_check_tie(monkeypatch, tmp_path, capsys):
    _run_check_verdict(monkeypatch, tmp_path, {"24h": 2900, "in_memory": 2900})
    code = _run(monkeypatch, ["--check", "--state", str(tmp_path / "probe.json")])
    assert code == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "TIE"


def test_check_both_miss(monkeypatch, tmp_path, capsys):
    _run_check_verdict(monkeypatch, tmp_path, {"24h": 0, "in_memory": 0})
    code = _run(monkeypatch, ["--check", "--state", str(tmp_path / "probe.json")])
    assert code == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "BOTH-MISS"
