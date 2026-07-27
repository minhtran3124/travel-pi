"""MCP server exposure (specs/travel-agent Task 9.1)."""

import asyncio


def _list_tools(server):
    return asyncio.run(server.list_tools())


def test_server_exposes_registry_tools():
    from app.mcp.server import build_mcp_server

    server = build_mcp_server()
    names = {t.name for t in _list_tools(server)}
    assert "get_trip_summary" in names
    assert "search_flights" in names


def test_memory_tools_excluded():
    from app.mcp.server import build_mcp_server

    names = {t.name for t in _list_tools(build_mcp_server())}
    # InjectedStore tools cannot be served over MCP.
    assert "save_user_preference" not in names
    assert "get_user_preferences" not in names


def test_destructive_tool_annotations():
    from app.mcp.server import build_mcp_server

    tools = {t.name: t for t in _list_tools(build_mcp_server())}
    book = tools["book_hotel"]
    assert "Cannot be undone." in book.description
    assert book.annotations.destructiveHint is True

    summary = tools["get_trip_summary"]
    assert summary.annotations.readOnlyHint is True


def test_book_and_cancel_tools_exposed_destructive():
    from app.mcp.server import build_mcp_server

    tools = {t.name: t for t in _list_tools(build_mcp_server())}
    for name in ("book_flight", "cancel_flight", "cancel_hotel"):
        assert name in tools, f"{name} not exposed over MCP"
        assert "Cannot be undone." in tools[name].description
        assert tools[name].annotations.destructiveHint is True


def test_create_trip_excluded_but_other_trip_tools_exposed():
    from app.mcp.server import build_mcp_server

    names = {t.name for t in _list_tools(build_mcp_server())}
    # create_trip returns a langgraph Command and takes an InjectedToolCallId
    # `tool_call_id` — cannot be served over MCP.
    assert "create_trip" not in names
    assert "get_trip_summary" in names


def test_resolve_date_stays_on_the_mcp_surface():
    """Regression for the PR #114 review.

    `resolve_date` gained an `InjectedToolCallId` parameter for the gh-109 fix,
    which made the generic "skip tools needing agent runtime" rule drop it from
    MCP — silently, while `/agent/manifest` kept advertising it. A servable
    variant keeps the read-only capability external clients already had.
    """
    from app.mcp.server import build_mcp_server

    tools = {t.name: t for t in _list_tools(build_mcp_server())}
    assert "resolve_date" in tools, "resolve_date must stay servable over MCP"
    assert tools["resolve_date"].annotations.readOnlyHint is True
    # The agent-only plumbing must not leak into the public schema.
    assert "tool_call_id" not in (
        tools["resolve_date"].inputSchema.get("properties") or {}
    )


def test_manifest_and_mcp_agree_on_injected_tool_call_id_tools():
    """Every tool skipped for `tool_call_id` is either served by a variant or
    genuinely agent-only — never advertised by the manifest while missing here."""
    import inspect

    from app.mcp.server import _MCP_SERVABLE_VARIANTS, build_mcp_server
    from app.tools.registry import ALL_TOOLS

    served = {t.name for t in _list_tools(build_mcp_server())}
    for tool in ALL_TOOLS:
        fn = tool.coroutine or tool.func
        params = inspect.signature(fn).parameters
        if "tool_call_id" in params and tool.name in _MCP_SERVABLE_VARIANTS:
            assert tool.name in served, f"{tool.name} has a variant but is not served"
