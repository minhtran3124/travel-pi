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
