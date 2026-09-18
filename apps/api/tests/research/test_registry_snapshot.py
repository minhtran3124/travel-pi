"""SC-26 non-replacement oracle: the tool registry, /agent/manifest payload and MCP
surface must equal the snapshot captured before the research feature was added."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.mcp.server import build_mcp_server
from app.routers.agent import agent_manifest
from app.tools.registry import ALL_TOOLS

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "tools_snapshot.json"


def _snapshot() -> dict:
    return json.loads(_FIXTURE.read_text())


def test_all_tools_unchanged() -> None:
    assert sorted(t.name for t in ALL_TOOLS) == _snapshot()["all_tools"]


def test_manifest_unchanged() -> None:
    assert agent_manifest().model_dump(mode="json") == _snapshot()["manifest"]


def test_mcp_tools_unchanged() -> None:
    live = sorted(t.name for t in asyncio.run(build_mcp_server().list_tools()))
    assert live == _snapshot()["mcp"]
