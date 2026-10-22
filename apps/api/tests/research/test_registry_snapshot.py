"""SC-26 non-replacement oracle: the tool registry, /agent/manifest payload and MCP
surface must equal the snapshot captured before the research feature was added."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.mcp.server import build_mcp_server
from app.routers.agent import agent_manifest
from app.tools.registry import ALL_TOOLS

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "tools_snapshot.json"


def _snapshot() -> dict:
    return json.loads(_FIXTURE.read_text())


@pytest.fixture(autouse=True)
def _reset_settings():
    yield
    get_settings.cache_clear()


def _set_flag(monkeypatch, *, enabled: bool) -> None:
    # Pin the flag explicitly — do NOT lean on the default, which 7.2 flips to True.
    monkeypatch.setenv("RESEARCH_ENABLED", "true" if enabled else "false")
    get_settings.cache_clear()


def test_all_tools_unchanged() -> None:
    assert sorted(t.name for t in ALL_TOOLS) == _snapshot()["all_tools"]


def test_manifest_byte_identical_when_flag_off(monkeypatch) -> None:
    """Non-replacement: with research disabled the manifest equals the pre-feature
    snapshot byte-for-byte — the research launcher is invisible."""
    _set_flag(monkeypatch, enabled=False)
    assert agent_manifest().model_dump(mode="json") == _snapshot()["manifest"]


def test_manifest_adds_only_research_subagent_when_flag_on(monkeypatch) -> None:
    """With research enabled the manifest differs from the snapshot in exactly one
    declared way: 'research' appended to subagents; tools stay identical."""
    _set_flag(monkeypatch, enabled=True)
    live = agent_manifest().model_dump(mode="json")
    snapshot = _snapshot()["manifest"]

    assert live["tools"] == snapshot["tools"]
    assert live["subagents"] == [*snapshot["subagents"], "research"]
    # No other key changed.
    assert set(live) == set(snapshot)
    assert {k: v for k, v in live.items() if k != "subagents"} == {
        k: v for k, v in snapshot.items() if k != "subagents"
    }


def test_mcp_tools_unchanged() -> None:
    live = sorted(t.name for t in asyncio.run(build_mcp_server().list_tools()))
    assert live == _snapshot()["mcp"]
