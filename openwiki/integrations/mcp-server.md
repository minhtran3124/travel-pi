---
type: integration
title: MCP server exposure of agent tools
description: How the standalone Model Context Protocol server publishes the agent's tool registry to external clients, which tools are withheld (destructive booking and cancellation tools, tools needing an injected store or tool-call id, and the by-name exclusion of list_trips and the two live web-search tools) and why the unauthenticated surface forces those choices, how read-only and destructive annotations are derived from tool metadata, and how the same registry feeds the agent's public manifest.
tags: [mcp, tools, integration, security, registry, annotations]
sources:
  - id: openwiki-source-9d08d722fd7b0056ba5981b9
    resource: repo://apps/api/app/mcp/server.py
  - id: openwiki-source-40fb538510ad8b559a8e282e
    resource: repo://apps/api/app/routers/agent.py
  - id: openwiki-source-97b1fd4b365c73190c64c4c1
    resource: repo://apps/api/app/tools/registry.py
  - id: openwiki-source-3b89cfbd1d5116099ae2bca0
    resource: repo://apps/api/app/tools/trip_tools.py
  - id: openwiki-source-874d3e2f46ad3afec7649d3a
    resource: repo://apps/api/tests/tools/test_clarification_tools.py
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
---

# MCP server exposure of agent tools

`apps/api/app/mcp/server.py` turns the agent's tool registry into a **FastMCP** server so external MCP clients (an IDE, another agent) can call the same travel tools the specialists use. It is a separate process, run with `python -m app.mcp.server`, not a FastAPI route, and it has **no authentication of its own**; every exclusion below follows from that fact.

## What is published

`build_mcp_server(name="travel-pi")` iterates `ALL_TOOLS` from `app/tools/registry.py`, the single source of truth for tool membership (see [Specialist sub-agents and the tool registry](../agent/specialists-and-tools.md)). For each tool it registers the underlying coroutine or function under the tool's name with its description and two `ToolAnnotations` derived from `TOOL_METADATA`: `readOnlyHint` (true for anything not in the registry's write set) and `destructiveHint` (true for the booking and cancellation tools). Destructive tools additionally get "Cannot be undone." appended to their description, though in practice they are never registered, as explained next. Because membership is registry-driven, a tool added to any specialist's group appears over MCP automatically unless one of the exclusion rules removes it.

## What is withheld, and why

FastMCP serves a function's **raw signature**, so any parameter that LangGraph would normally inject at runtime becomes an argument the remote caller supplies. Three rules keep that from turning into a security hole:

1. **Tools that need an injected `store` or `tool_call_id` are skipped.** An external client can supply neither the long-term memory store nor a LangGraph tool-call id, so the memory tools and the clarification signal tool cannot function over MCP. (The clarification tool is additionally kept out of the registry altogether, so it never reaches this check.)
2. **Destructive tools are not exposed.** `book_flight`, `book_hotel`, `cancel_flight` and `cancel_hotel` require an authenticated owner and, on the agent path, run behind the human-in-the-loop plan approval and the premium tier gate. The unauthenticated MCP surface can provide none of that, so booking and cancellation stay on the in-agent path (see [Guardrails](../agent/guardrails-pii-and-hitl.md) and [Bookings, flights and hotels](../domain/bookings-flights-and-hotels.md)).
3. **`list_trips` is excluded by name.** Its `user_id` is an injected owner argument on the agent path, but over MCP it would be caller-supplied, and that single argument would be enough to enumerate any user's trips. Other trip-scoped tools survive because they need a `trip_id` the caller cannot guess and return a plain `no_active_trip` guidance dict when it is absent, but they should be read with the same caution: an injected `user_id` on the MCP surface is an untrusted input.
4. **The live web-search tools are excluded by name too.** `search_web` and `find_places_live` take an injected `user_id` that drives their per-user hourly limit and spends paid provider quota. Over MCP that id would be caller-supplied, so they are withheld next to `list_trips` (see [Live web search](live-web-search.md)).

The trip-research deep agent does not change this surface. It binds a read-only subset of the existing registry and registers nothing new, and its grader-only `validate_proposal` tool is never added to the registry (see [Trip-research deep agent](../agent/trip-research-deep-agent.md)).

`tests/mcp/` and `tests/tools/test_clarification_tools.py` pin that destructive tools and the clarification tool stay off the server.

## The read-only surface in practice

What remains is the search and lookup set: flight search, hotel browse and availability, place search and nearby lookup, weather, climate, air quality, routing, visa, tips, currency and the travel-knowledge retrieval tool. These call the same services as the REST API, open their own database session per call, and return the same JSON-able shapes (see [Destinations, places and travel information](../domain/destinations-places-and-travel-info.md)). Panel-capable tools return their `(summary, artifact)` pair; over MCP only the content is meaningful.

## The manifest twin

The authenticated `GET /agent/manifest` endpoint publishes the same registry to the web client: specialist names plus every tool's name, first description line and the same `read_only`/`destructive` flags. Both surfaces therefore change together when `TOOLS_BY_DOMAIN`, `_WRITE` or `_DESTRUCTIVE` change (see [Agent chat endpoints, SSE streaming and side panels](../agent/streaming-and-side-panels.md)).

## Adding a tool safely

Before adding a tool to the registry, decide whether it is safe to serve unauthenticated: if it writes, mark it in `_WRITE`; if it is irreversible, mark it in `_DESTRUCTIVE` so it is withheld; if it takes an injected owner id that alone unlocks user data, add it to `_MCP_EXCLUDED_BY_NAME`. Injected-store and tool-call-id tools exclude themselves.
