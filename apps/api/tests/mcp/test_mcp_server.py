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
