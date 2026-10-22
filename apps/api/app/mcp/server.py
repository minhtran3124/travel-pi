"""MCP server exposing the agent's tool registry to external clients.

Run as a standalone MCP server:  python -m app.mcp.server
"""

from __future__ import annotations

import inspect

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.tools.registry import ALL_TOOLS, TOOL_METADATA

# Excluded by name: FastMCP serves the raw signature, so an injected user_id becomes a caller-supplied
# arg on this unauthenticated surface — and list_trips would need only that to dump a user's inventory.
_MCP_EXCLUDED_BY_NAME = {
    "list_trips",
    "search_web",
    "find_places_live",
}


def build_mcp_server(name: str = "travel-pi") -> FastMCP:
    """Build a FastMCP server exposing the registry tools."""
    server = FastMCP(name)
    for tool in ALL_TOOLS:
        meta = TOOL_METADATA[tool.name]
        description = (tool.description or "").strip()
        if meta["destructive"]:
            description += " Cannot be undone."
        fn = tool.coroutine or tool.func
        # Tools needing a runtime-injected `store` or `tool_call_id` can't be served over MCP:
        # an external client can supply neither.
        params = inspect.signature(fn).parameters
        if "store" in params or "tool_call_id" in params:
            continue
        # Destructive tools are not exposed: the unauthenticated MCP surface cannot supply the
        # authenticated owner they require, so keep booking/cancellation to the in-agent HITL path.
        if meta["destructive"]:
            continue
        if tool.name in _MCP_EXCLUDED_BY_NAME:
            continue
        server.add_tool(
            fn,
            name=tool.name,
            description=description,
            annotations=ToolAnnotations(
                readOnlyHint=meta["readOnly"],
                destructiveHint=meta["destructive"],
            ),
        )
    return server


mcp_server = build_mcp_server()


if __name__ == "__main__":
    mcp_server.run()
