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

# Tools excluded from the MCP surface by name (beyond the structural skips
# below). `build_mcp_server` registers `tool.func`, and FastMCP derives the
# served input schema from the RAW signature — the `InjectedState` annotation is
# invisible to it, so an injected `user_id` becomes an ordinary caller-supplied
# argument. That surface is unauthenticated (standalone `python -m
# app.mcp.server`, not mounted in `main.py`). Every other read tool shares this,
# but they also need a guessed trip UUID; `list_trips` would need only a
# `user_id` to dump a user's whole trip inventory
# (specs/gh-166-list-trips-tool E003-B).
_MCP_EXCLUDED_BY_NAME = {"list_trips"}


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
        # Destructive tools (booking/cancellation — real money and reservations)
        # are NOT exposed over MCP. The MCP surface is unauthenticated and cannot
        # supply the authenticated owner these actions now require (they inject
        # user_id from the agent's graph state), so an external client could only
        # ever book/cancel with no valid owner — or, worse, if that gap were
        # closed, act without an authorization boundary. Keep destructive actions
        # to the in-agent HITL path only (specs/review-a-security-hardening E004).
        if meta["destructive"]:
            continue
        # Read tools whose only argument would be a caller-supplied `user_id`
        # (see _MCP_EXCLUDED_BY_NAME above).
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
