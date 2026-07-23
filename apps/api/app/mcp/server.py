"""MCP server — expose agent tools to external clients (specs/travel-agent Task 9.1).

Wraps the same tool registry the agent uses (single source of truth) as an MCP
server, so a Claude Desktop / Agent-SDK client can call the travel backend
directly. Each tool carries MCP annotations (readOnly / destructive, per roadmap
B1); destructive tools say so in the description. InjectedStore tools (long-term
memory) are skipped — they need the agent's runtime store, not an external call.

Run as a standalone MCP server:  python -m app.mcp.server
"""

from __future__ import annotations

import inspect

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.tools.registry import ALL_TOOLS, TOOL_METADATA


def build_mcp_server(name: str = "travel-pi") -> FastMCP:
    """Build a FastMCP server exposing the registry tools.

    :param name: The MCP server name advertised to clients.
    :return: The configured FastMCP server.
    """
    server = FastMCP(name)
    for tool in ALL_TOOLS:
        meta = TOOL_METADATA[tool.name]
        description = (tool.description or "").strip()
        if meta["destructive"]:
            description += " Cannot be undone."
        fn = tool.coroutine or tool.func
        # InjectedStore tools carry a runtime-only `store` param in their
        # signature (hidden from the LLM schema) — they can't be served over MCP.
        # Tools with an InjectedToolCallId `tool_call_id` param return a langgraph
        # `Command` and need the agent's runtime tool-call id — also not servable
        # over MCP (an external client can't supply one).
        params = inspect.signature(fn).parameters
        if "store" in params or "tool_call_id" in params:
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
