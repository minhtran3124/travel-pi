---
type: Integration
title: Live web search (Tavily and SerpAPI)
description: The concierge's last-resort live web tools. search_web uses Tavily for general facts, news and events; find_places_live uses SerpAPI Google Maps for venues. The page covers flag-and-key availability filtering, the per-user hourly limit, the in-process TTL cache, error mapping to transient and logic failures, escaping of untrusted content, and exclusion from MCP.
tags: [integration, web-search, tavily, serpapi, concierge, tools, rate-limiting, security]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
sources:
  - id: openwiki-source-5300fab0b97a7cfb93201ea7
    resource: repo://apps/api/app/core/config.py
  - id: openwiki-source-9d08d722fd7b0056ba5981b9
    resource: repo://apps/api/app/mcp/server.py
  - id: openwiki-source-7c5c6e9b81adf165d7c55936
    resource: repo://apps/api/app/services/web_search_service.py
  - id: openwiki-source-97b1fd4b365c73190c64c4c1
    resource: repo://apps/api/app/tools/registry.py
  - id: openwiki-source-e367aa7aabde754472afac4e
    resource: repo://apps/api/app/tools/web_search_tools.py
  - id: openwiki-source-94287341de6c23aae5de3514
    resource: repo://apps/api/tests/tools/test_web_search_binding.py
generated: { by: "claude-code", at: "2026-09-25T03:45:43.723Z" }
---

# Live web search (Tavily and SerpAPI)

Almost everything the agent knows comes from seeded reference data or keyless public APIs (see [Destinations, places and travel information](../domain/destinations-places-and-travel-info.md)). Live web search is the exception: a **last-resort, off-by-default** path to two paid providers, bound only to the concierge.

| Tool | Provider | Use |
|---|---|---|
| `search_web(query, topic, time_range, domains)` | Tavily (`tavily-python`, async client) | General facts, recent news and advisories (`topic="news"`), and current or upcoming events and festivals (`topic="general"` with the city and month in the query) |
| `find_places_live(query, near)` | SerpAPI Google Maps engine (official `serpapi` SDK) | Venues, restaurants and shops near a place, with rating, reviews, address and hours |

<!-- openwiki: broken internal link [url] file "url" does not exist. Fix the href or restore the target, then delete this comment. -->
Both tool docstrings, and the concierge prompt that teaches when to use them, restrict them to cases where the internal tools returned nothing or the question is time-sensitive. They also forbid using them for flight or hotel prices, forbid putting the traveller's name or contact details in a query, and require every web fact to be cited as `[title](url)` (see [Prompt registry](../agent/prompt-registry.md)).

## Availability: flag plus key, checked at graph build

`WEB_SEARCH_ENABLED` is false by default. A provider is **available** only when the flag is on and its key (`TAVILY_API_KEY`, `SERPAPI_API_KEY`) is non-blank (`tavily_search_available`, `serpapi_search_available`). `get_tools_for` passes every domain group through `available()` in `app/tools/registry.py`. That function drops `search_web` without Tavily and `find_places_live` without SerpAPI, and it reads settings at call time, so a change applies on the next graph build. With the flag off, the concierge's bound tools are exactly what they were before the feature existed. The service re-checks availability and raises `WebSearchError` if a call slips through (see [Specialist sub-agents and the tool registry](../agent/specialists-and-tools.md) and [Configuration and environments](../architecture/configuration-and-environments.md)).

## A call, step by step (`app/tools/web_search_tools.py`)

1. **Signed-in traveller required.** `user_id` is injected from graph state and hidden from the model's schema, along with `language` for places. With no user id, the tool raises a `ToolException` instead of searching anonymously.
2. **Per-user hourly limit.** `enforce_rate_limit` runs on a fresh `session_scope()` session (bucket `web_search`, `WEB_SEARCH_USER_HOURLY_LIMIT` hits per 3600 s, default 30) before any provider call. It uses the same DB-backed fixed-window limiter as HTTP routes (see [Rate limiting and quotas](../concepts/rate-limiting-and-quotas.md)).
3. **Service call** (`app/services/web_search_service.py`). The service does no rate limiting; it handles the cache, the provider call and error mapping.
4. **Rendering.** Results come back as `content_and_artifact`. The model reads one `<web_result source="…" title="…">…</web_result>` block per item, and the raw mapped result is the artifact. At most 5 items are returned per provider.

## Treating provider output as untrusted

Provider text is third-party content that ends up in the model's context. Every value, URL and title included, is `html.escape`d with quotes. Snippets are capped at 500 characters, and URLs are loosely bounded at 2048 characters so they are never cut mid-identifier. Wrapping each item in a `<web_result>` element lets the concierge prompt tell the model to treat that content as data, never as instructions. Nothing in this path logs the query, the results, the user id or a key. The only log lines are provider, engine, cache hit or miss, latency and count. This is the one tool path that marks its output as untrusted; tool and RAG output in general is not wrapped (see [Guardrails](../agent/guardrails-pii-and-hitl.md)).

## Cache and error mapping

The service keeps one in-process dict of `key → (expires_at, value)`, using a monotonic clock and bounded by `WEB_SEARCH_CACHE_MAX_ENTRIES` (512, oldest first). Keys include the provider, engine, case-folded query and every parameter. Tavily news results expire after `WEB_SEARCH_NEWS_CACHE_TTL_SECONDS` (900); everything else after `WEB_SEARCH_CACHE_TTL_SECONDS` (3600). The cache is per process and is lost on restart.

Provider failures map to two classes:

- **`WebSearchUpstreamError`** (a subclass of `UpstreamError`, HTTP 502): timeouts, connection errors, 5xx responses, and malformed 200 bodies (non-JSON or scalar JSON). The tool **re-raises** it, so the concierge's graph retry policy for `UpstreamError` retries the node (see [Specialist sub-agents and the tool registry](../agent/specialists-and-tools.md)).
- **`WebSearchError`** (HTTP 502, not transient): a bad key, forbidden access, an exhausted quota, or a bad request. The tool folds it, like any other `AppError` including a `RateLimitError`, into a tool error through `tool_error`, keeping the hint *"Answer from the other sources and say that live web results were unavailable."*

Client construction happens outside the `try` block, so a misconfiguration such as a bad proxy setting surfaces as a permanent error rather than being retried. SerpAPI's "hasn't returned any results" error, returned on an HTTP 200 or as an HTTP error, is mapped to an empty result, not a failure. A single-venue Maps response (`place_results`) is mapped to a one-item list, and a place without a website gets a Google Maps `place_id` URL.

## Not on MCP

The MCP server serves raw tool signatures, so an injected `user_id` would become an argument the caller controls on an unauthenticated surface. `search_web` and `find_places_live` are therefore in `_MCP_EXCLUDED_BY_NAME`, next to `list_trips` (see [MCP server exposure](mcp-server.md)).

## Tests and evaluation

`tests/tools/test_web_search_tools.py` (escaping, capping, the signed-in guard, the rate limit and error folding), `tests/tools/test_web_search_binding.py` (flag and key filtering of the concierge's tools), `tests/services/test_web_search_service.py` (the cache, TTLs and eviction, and the error mapping for both SDKs) and `tests/core/test_config_web_search.py` (the availability properties). `eval/datasets/web_search.json` holds the web-search goldens for the agent eval (see [Agent evaluation harness](../testing/agent-eval-harness.md)).
