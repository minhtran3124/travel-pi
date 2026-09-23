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


def test_read_only_annotation_preserved():
    from app.mcp.server import build_mcp_server

    tools = {t.name: t for t in _list_tools(build_mcp_server())}
    summary = tools["get_trip_summary"]
    assert summary.annotations.readOnlyHint is True


def test_destructive_book_and_cancel_tools_excluded():
    # specs/review-a-security-hardening E004: destructive booking/cancellation
    # tools are NOT exposed over the unauthenticated MCP surface.
    from app.mcp.server import build_mcp_server

    names = {t.name for t in _list_tools(build_mcp_server())}
    for name in ("book_flight", "book_hotel", "cancel_flight", "cancel_hotel"):
        assert name not in names, f"{name} must not be exposed over MCP"


def test_create_trip_excluded_but_other_trip_tools_exposed():
    from app.mcp.server import build_mcp_server

    names = {t.name for t in _list_tools(build_mcp_server())}
    # create_trip returns a langgraph Command and takes an InjectedToolCallId
    # `tool_call_id` — cannot be served over MCP.
    assert "create_trip" not in names
    assert "get_trip_summary" in names


def test_budget_tools_exposed():
    """estimate_trip_budget (readOnly) and set_trip_budget (write, non-destructive)
    are served over MCP (specs/agent-budget-trip-context SC-7)."""
    from app.mcp.server import build_mcp_server

    tools = {t.name: t for t in _list_tools(build_mcp_server())}
    assert tools["estimate_trip_budget"].annotations.readOnlyHint is True
    assert tools["set_trip_budget"].annotations.readOnlyHint is False
    assert tools["set_trip_budget"].annotations.destructiveHint is False


def test_web_search_tools_excluded_and_count_unchanged():
    # specs/agent-web-search SC-8: the live web-search tools carry an InjectedState
    # `user_id` that FastMCP would expose as a caller-supplied arg on the
    # unauthenticated surface, so they are kept off it. Adding them to the registry
    # must not change the served tool count.
    from app.mcp.server import build_mcp_server

    names = {t.name for t in _list_tools(build_mcp_server())}
    for name in ("search_web", "find_events", "find_places_live"):
        assert name not in names, f"{name} must not be exposed over MCP"
    assert len(names) == 28  # recorded before web-search tools entered the registry


def test_list_trips_excluded_but_other_read_tools_exposed():
    # specs/gh-166-list-trips-tool E003-B: FastMCP derives the served schema from
    # the raw signature, so the InjectedState `user_id` would become a
    # caller-supplied argument on an unauthenticated surface — and `list_trips`
    # needs nothing else to dump a user's whole trip inventory.
    from app.mcp.server import build_mcp_server

    names = {t.name for t in _list_tools(build_mcp_server())}
    assert "list_trips" not in names
    assert "get_trip_summary" in names
    assert "search_flights" in names
    assert "estimate_trip_budget" in names
