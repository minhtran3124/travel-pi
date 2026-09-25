"""SC-1 — the ``claude_cli`` wrapper, exercised through the fake ``claude``.

Every test replaces ``claude`` with ``fixtures/fake_claude.py`` via
``SIM_CLAUDE_BIN`` and stays fully offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sim import claude_cli

FAKE = Path(__file__).parent / "fixtures" / "fake_claude.py"
SCHEMA = {"type": "object", "properties": {"message": {"type": "string"}}}


@pytest.fixture(autouse=True)
def _reset_quota():
    claude_cli.last_quota = None
    yield
    claude_cli.last_quota = None


@pytest.fixture()
def fake_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_CLAUDE_BIN", str(FAKE))
    argv_file = tmp_path / "argv.json"
    calls_file = tmp_path / "calls.txt"
    monkeypatch.setenv("FAKE_CLAUDE_ARGV_FILE", str(argv_file))
    monkeypatch.setenv("FAKE_CLAUDE_CALLS_FILE", str(calls_file))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_OUTPUT_FILE", raising=False)
    return {"argv": argv_file, "calls": calls_file, "tmp": tmp_path}


async def _run():
    return await claude_cli.run(
        system_prompt="you are a traveller",
        user_prompt="hello",
        schema=SCHEMA,
    )


def _flag_value(argv, flag):
    return argv[argv.index(flag) + 1]


@pytest.mark.asyncio
async def test_argv_holds_the_full_mandated_flag_set(fake_env):
    await _run()
    argv = json.loads(fake_env["argv"].read_text())
    assert "--bare" not in argv
    for flag in (
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--verbose",
    ):
        assert flag in argv
    assert _flag_value(argv, "--tools") == ""
    assert _flag_value(argv, "--setting-sources") == ""
    assert _flag_value(argv, "--output-format") == "stream-json"
    assert _flag_value(argv, "--model") == "sonnet"
    assert _flag_value(argv, "--system-prompt") == "you are a traveller"
    assert json.loads(_flag_value(argv, "--json-schema")) == SCHEMA


@pytest.mark.asyncio
async def test_model_flag_defaults_to_sonnet(fake_env, monkeypatch):
    monkeypatch.delenv("SIM_CLAUDE_MODEL", raising=False)
    await _run()
    argv = json.loads(fake_env["argv"].read_text())
    assert argv[argv.index("--model") + 1] == "sonnet"


@pytest.mark.asyncio
async def test_last_quota_five_hour_from_env(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIVE_HOUR", "0.6")
    await _run()
    assert claude_cli.last_quota.five_hour == 0.6
    assert claude_cli.last_quota.seven_day == 0.33
    assert claude_cli.last_quota.resets_at == "2026-09-25T12:00:00Z"


@pytest.mark.asyncio
async def test_rate_limited_raises_quota_exhausted(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "rate_limited")
    with pytest.raises(claude_cli.QuotaExhausted):
        await _run()


@pytest.mark.asyncio
async def test_output_file_drives_returned_value(fake_env, monkeypatch):
    out = fake_env["tmp"] / "out.json"
    out.write_text(json.dumps({"message": "bonjour"}))
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT_FILE", str(out))
    result = await _run()
    assert result == {"message": "bonjour"}


@pytest.mark.asyncio
async def test_output_list_consumed_one_per_call(fake_env, monkeypatch):
    out = fake_env["tmp"] / "out.json"
    out.write_text(json.dumps([{"message": "one"}, {"message": "two"}]))
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT_FILE", str(out))
    assert await _run() == {"message": "one"}
    assert await _run() == {"message": "two"}


@pytest.mark.asyncio
async def test_calls_file_gains_one_line_per_call(fake_env):
    await _run()
    await _run()
    lines = [ln for ln in fake_env["calls"].read_text().splitlines() if ln]
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_bad_json_raises_driver_error(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "bad_json")
    with pytest.raises(claude_cli.DriverError):
        await _run()


@pytest.mark.asyncio
async def test_array_shape_output_is_parsed(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "array_shape")
    out = fake_env["tmp"] / "out.json"
    out.write_text(json.dumps({"message": "arr"}))
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT_FILE", str(out))
    assert await _run() == {"message": "arr"}
    assert claude_cli.last_quota.five_hour == 0.4


@pytest.mark.asyncio
async def test_timeout_raises_driver_error(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SLEEP", "3")
    with pytest.raises(claude_cli.DriverError):
        await claude_cli.run(
            system_prompt="s",
            user_prompt="u",
            schema=SCHEMA,
            timeout=0.3,
        )


@pytest.mark.asyncio
async def test_warning_status_still_returns_and_updates_quota(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "warn")
    monkeypatch.setenv("FAKE_CLAUDE_FIVE_HOUR", "0.9")
    result = await _run()
    assert result == {"ok": True}
    assert claude_cli.last_quota.five_hour == 0.9


@pytest.mark.asyncio
async def test_is_error_rate_limit_result_raises_quota_exhausted(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "error_rate_limit")
    with pytest.raises(claude_cli.QuotaExhausted):
        await _run()


@pytest.mark.asyncio
async def test_non_rate_error_result_maps_to_driver_error(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "error_other")
    with pytest.raises(claude_cli.DriverError):
        await _run()


@pytest.mark.asyncio
async def test_malformed_line_among_valid_ones_is_tolerated(fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "mixed")
    out = fake_env["tmp"] / "out.json"
    out.write_text(json.dumps({"message": "mixed"}))
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT_FILE", str(out))
    assert await _run() == {"message": "mixed"}


@pytest.mark.asyncio
async def test_missing_binary_raises_driver_error(fake_env, monkeypatch):
    monkeypatch.setenv("SIM_CLAUDE_BIN", str(fake_env["tmp"] / "no-such-claude"))
    with pytest.raises(claude_cli.DriverError):
        await _run()


def test_cli_version_missing_binary_raises_driver_error(fake_env, monkeypatch):
    monkeypatch.setenv("SIM_CLAUDE_BIN", str(fake_env["tmp"] / "no-such-claude"))
    with pytest.raises(claude_cli.DriverError):
        claude_cli.cli_version()


def test_cli_version_reads_the_binary(fake_env):
    assert claude_cli.cli_version().startswith("1.2.3")
