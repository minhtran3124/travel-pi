"""Two-phase A/B prompt-cache retention probe (specs/prompt-caching-system-prefix Task 2.2).

Offline: ``_build_chat_model`` is monkeypatched to a stub whose ``AIMessage``
carries ``usage_metadata.input_token_details.cache_read`` per retention arm, and
``time.time`` is controlled to drive the elapsed-gap logic. No network, no key.
"""

import json

import pytest
import scripts.probe_cache_retention as mod

_VERDICT_TOKENS = ("RETENTION-WINS", "TIE", "BOTH-MISS", "CONTROL-ONLY")


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


def _make_build_second_arm_raises(calls: dict[str, list]):
    """Build models where the FIRST arm (24h) succeeds and the SECOND (control)
    raises on invoke — simulating a network/5xx failure after the first arm's
    call already refreshed its cache entry."""

    def _fake(provider, model, *, model_kwargs=None, **kw):
        value = (model_kwargs or {})["prompt_cache_retention"]
        calls.setdefault(value, [])
        if value == mod.RETENTION_CONTROL:
            return _RaisingModel(calls[value])
        return _StubModel(2900, calls[value])

    return _fake


class _RaisingModel:
    def __init__(self, calls: list) -> None:
        self._calls = calls

    def invoke(self, prompt):
        self._calls.append(prompt)
        raise RuntimeError("simulated provider error on the second arm")


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
    # both arms' second call must read cached tokens or seed refuses to write
    monkeypatch.setattr(
        mod, "_build_chat_model", _make_build({"24h": 2900, "in_memory": 2900}, calls)
    )
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


def test_seed_refuses_when_an_arm_not_warmed(monkeypatch, tmp_path, capsys):
    """Important 1: a second-call zero-read means the write never landed."""
    monkeypatch.setattr(
        mod, "_build_chat_model", _make_build({"24h": 2900, "in_memory": 0}, {})
    )
    monkeypatch.setattr("time.time", lambda: 1000.0)
    state = tmp_path / "probe.json"

    code = _run(monkeypatch, ["--seed", "--state", str(state), "--model", "fake"])

    assert code == 3
    assert not state.exists()  # no state file written when a seed did not warm
    out = capsys.readouterr().out
    assert "in_memory" in out and "re-seed" in out.lower()


def test_check_exits_2_below_min_gap(monkeypatch, tmp_path):
    """Minor B: too-soon returns before any stamp, so the experiment is unspent."""
    state = tmp_path / "probe.json"
    _write_state(state, seeded_at=1000.0)
    monkeypatch.setattr(mod, "_build_chat_model", _make_build({}, {}))
    monkeypatch.setattr("time.time", lambda: 1000.0 + 30 * 60)  # 30 min < 60

    code = _run(monkeypatch, ["--check", "--state", str(state)])

    assert code == 2
    # An early check must NOT spend the experiment: no attempt marker written.
    data = json.loads(state.read_text())
    assert "attempted_at" not in data
    assert "checked_at" not in data


def test_check_boundary_exact_min_gap_verdicts(monkeypatch, tmp_path, capsys):
    """Minor: gate is ``elapsed < min_gap``, so exactly the minimum passes."""
    state = tmp_path / "probe.json"
    _write_state(state, seeded_at=1000.0)
    monkeypatch.setattr(
        mod, "_build_chat_model", _make_build({"24h": 2900, "in_memory": 0}, {})
    )
    monkeypatch.setattr("time.time", lambda: 1000.0 + 60 * 60)  # exactly 60 min

    code = _run(monkeypatch, ["--check", "--state", str(state)])

    assert code == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "RETENTION-WINS"


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


def test_check_control_only(monkeypatch, tmp_path, capsys):
    """Important 3: only the control arm hits — the fourth table cell."""
    _run_check_verdict(monkeypatch, tmp_path, {"24h": 0, "in_memory": 2900})
    code = _run(monkeypatch, ["--check", "--state", str(tmp_path / "probe.json")])
    assert code == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "CONTROL-ONLY"


def test_second_check_is_refused(monkeypatch, tmp_path, capsys):
    """Important 2: a check refreshes the cache, so a re-check must be refused."""
    state = tmp_path / "probe.json"
    _write_state(state, seeded_at=1000.0)
    monkeypatch.setattr(
        mod, "_build_chat_model", _make_build({"24h": 2900, "in_memory": 2900}, {})
    )
    monkeypatch.setattr("time.time", lambda: 1000.0 + 61 * 60)

    assert _run(monkeypatch, ["--check", "--state", str(state)]) == 0
    capsys.readouterr()  # discard first verdict

    code = _run(monkeypatch, ["--check", "--state", str(state)])

    assert code == 3
    out = capsys.readouterr().out
    for token in _VERDICT_TOKENS:
        assert token not in out  # no verdict on a refused re-check
    assert "re-seed" in out.lower()


def test_check_partial_failure_stamps_attempt_and_refuses_recheck(
    monkeypatch, tmp_path, capsys
):
    """Important: a --check that crashes after touching the first arm's cache has
    spent the experiment. The attempt marker must be persisted BEFORE the first
    invoke, so a later --check refuses (exit 3) instead of printing a false
    RETENTION-WINS off the failed run's refreshed cache."""
    state = tmp_path / "probe.json"
    _write_state(state, seeded_at=1000.0)
    calls: dict[str, list] = {}
    monkeypatch.setattr(
        mod, "_build_chat_model", _make_build_second_arm_raises(calls)
    )
    monkeypatch.setattr("time.time", lambda: 1000.0 + 61 * 60)

    # The control arm raises after the 24h arm's call already refreshed its cache.
    with pytest.raises(RuntimeError):
        mod.check(state, 60.0)

    # The 24h arm was invoked (its cache is now refreshed); the attempt was stamped
    # before that call, so the crash cannot leave the experiment looking unspent.
    assert len(calls[mod.RETENTION_24H]) == 1
    data = json.loads(state.read_text())
    assert "attempted_at" in data
    assert "checked_at" not in data  # the run never completed

    # A later --check must refuse rather than report a verdict off the stale,
    # failure-refreshed 24h cache.
    monkeypatch.setattr(
        mod, "_build_chat_model", _make_build({"24h": 2900, "in_memory": 0}, {})
    )
    monkeypatch.setattr("time.time", lambda: 1000.0 + 62 * 60)
    code = _run(monkeypatch, ["--check", "--state", str(state)])

    assert code == 3
    out = capsys.readouterr().out
    for token in _VERDICT_TOKENS:
        assert token not in out  # no verdict on a refused re-check
    assert "re-seed" in out.lower()


def test_seed_removes_stale_state_when_refusing(monkeypatch, tmp_path, capsys):
    """Minor A: a refused (or crashed) seed must not leave a previous seed's state
    file in place for a later --check to trust as the new run."""
    state = tmp_path / "probe.json"
    _write_state(state, seeded_at=500.0)  # stale state from a previous seed
    assert state.exists()
    # in_memory arm stays cold, so this seed refuses to write a fresh state.
    monkeypatch.setattr(
        mod, "_build_chat_model", _make_build({"24h": 2900, "in_memory": 0}, {})
    )
    monkeypatch.setattr("time.time", lambda: 1000.0)

    code = _run(monkeypatch, ["--seed", "--state", str(state), "--model", "fake"])

    assert code == 3
    # The stale file is gone: it was removed at the start of --seed, before any
    # call, so no --check can mistake the old seed's nonces/clock for the new one.
    assert not state.exists()


def test_check_sends_the_same_prompt_seed_sent(monkeypatch, tmp_path):
    """Minor: the nonce must round-trip from --seed into each --check call."""
    calls: dict[str, list] = {}
    monkeypatch.setattr(
        mod, "_build_chat_model", _make_build({"24h": 2900, "in_memory": 2900}, calls)
    )
    state = tmp_path / "probe.json"

    monkeypatch.setattr("time.time", lambda: 1000.0)
    assert _run(monkeypatch, ["--seed", "--state", str(state), "--model", "fake"]) == 0
    data = json.loads(state.read_text())

    monkeypatch.setattr("time.time", lambda: 1000.0 + 61 * 60)
    assert _run(monkeypatch, ["--check", "--state", str(state)]) == 0

    for value in ("24h", "in_memory"):
        nonce = data["arms"][value]["nonce"]
        check_prompt = calls[value][-1]  # seed = 2 calls, check = the 3rd
        assert f"[probe-nonce:{nonce}]" in check_prompt
