---
type: operations
title: Admin API and server-rendered dashboard
description: The operator surfaces that sit beside the product API — the role-gated admin endpoint for setting a user's tier, and the Jinja2 dashboard under /dashboard that browses the seeded catalog with language switching, lists bookings, edits per-agent LLM configuration through a validated form whose save invalidates the running config cache, and inspects agent runs as cost and latency rollups and per-turn waterfalls with prompt attribution — plus how each surface is protected.
tags: [dashboard, admin, jinja2, agent-config, agent-runs, operations, basic-auth]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-a9279e30fdd03870c290e7ae
    resource: repo://apps/api/app/agents/graph.py
  - id: openwiki-source-eda0b38a403232caa7fc52bf
    resource: repo://apps/api/app/core/dashboard_auth.py
  - id: openwiki-source-dc7bdb77381316bc40fe8762
    resource: repo://apps/api/app/routers/admin.py
  - id: openwiki-source-28027e239e78744dcf88e06a
    resource: repo://apps/api/app/routers/dashboard.py
  - id: openwiki-source-7398073c9f62630d454539d1
    resource: repo://apps/api/app/services/agent_config_service.py
  - id: openwiki-source-d0499df6c06c07ffcc8979b5
    resource: repo://apps/api/tests/api/admin/test_admin_tier.py
  - id: openwiki-source-46ccba8d5524768c340c0c14
    resource: repo://apps/api/tests/api/agent_config/test_agent_config_dashboard.py
  - id: openwiki-source-2a67e3b02d7bf2619527f2bf
    resource: repo://apps/api/tests/api/agent_config/test_agent_config_service.py
  - id: openwiki-source-f463380d889849a2f19a0945
    resource: repo://apps/api/tests/api/agent_config/test_agent_run_detail_page.py
  - id: openwiki-source-2b3081b1456f8b24e516f24d
    resource: repo://apps/api/tests/api/agent_config/test_agent_runs_dashboard.py
  - id: openwiki-source-d968140805cafde77b835d0a
    resource: repo://apps/api/tests/api/agent_config/test_dashboard_auth.py
  - id: openwiki-source-fdb0d28ac06e15635b270c81
    resource: repo://apps/api/tests/api/routes/test_dashboard_language.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Admin API and server-rendered dashboard

Two operator surfaces exist alongside the JSON API, protected in two different ways.

## The admin endpoint

`routers/admin.py` exposes `PATCH /admin/users/{user_id}/tier`. It requires a valid Supabase bearer token whose `app_metadata.role` is `admin` (the top-level Postgres role claim is never consulted, see [Authentication and user tiers](../concepts/auth-and-tiers.md)); any other caller receives a 403 and an anonymous caller a 401. The handler upserts the raw tier string into the `users` table, reads it back, logs who changed it, and returns `{ user_id, tier }`. `tests/api/admin/test_admin_tier.py` covers the success, non-admin, missing-role, unauthenticated and invalid-tier cases. The `scripts/set_tier.py` module does the same from the command line without a token.

## The dashboard

`routers/dashboard.py` and `routers/dashboard_prompts.py` render Jinja2 templates from `app/templates/` under the `/dashboard` prefix. The router is **excluded from the OpenAPI schema** and every route carries `Depends(require_dashboard_access)`: HTTP Basic when `DASHBOARD_BASIC_USER` and `DASHBOARD_BASIC_PASSWORD` are set, open in development when they are not, and **404 in production when they are not**, so the pages are never reachable in production without credentials. `tests/api/agent_config/test_dashboard_auth.py` checks all of those outcomes, that non-ASCII credentials produce a 401 rather than a 500, and that valid credentials reach every dashboard route.

### Catalog browsing with a language switch

The catalog pages (flights board and search, flight detail, hotels, places, tips, visa, weather, air quality) call the same services as the REST API. A `?lang=` query parameter wins over a `dashboard_lang` cookie, which an explicit choice sets for a year; unknown codes normalize to the default. Hotel and place descriptions are localized through the content-translation store, and bounded vocabularies such as place categories use the same lookup tables the side panels use (see [Destinations, places and travel information](../domain/destinations-places-and-travel-info.md)). `tests/api/routes/test_dashboard_language.py` pins the query-then-cookie precedence and the seeded Vietnamese translations. A bookings page lists bookings across owners with the booking service's sort options, for operators only.

### Per-agent LLM configuration

`/dashboard/agent-config` lists every configurable node grouped into sections (main agent, domain sub-agents, support agents) as a card grid with an edit modal; the provider dropdown is the catalog's `PROVIDER_NAMES` and each provider's reference model list is passed to the template. `POST /dashboard/agent-config/{agent_name}` follows the post-redirect-get pattern: it first resolves the agent (404 before any write if unknown), then calls `AgentConfigService.update_config`, which validates the provider, temperature range and `max_tokens`, forces `base_url` to `NULL` (the client derives it from the profile), upserts the row and **invalidates `AgentConfigCache`**. A validation error re-renders the form with a 400; success redirects to the list with a saved banner. The `enabled` checkbox uses a hidden marker field so that a form which does not own the flag leaves it untouched, while an unchecked box on a form that does own it submits `False` (see [LLM providers and per-agent configuration](../agent/llm-providers-and-agent-config.md)).

Because the running agent resolves models per request through the cache, and `resolve_travel_graph` rebuilds the compiled graph when the cache's generation changes, a save here reaches live traffic within the poll interval **without a restart**, while conversation state is preserved because the checkpointer and store are reused. The `reflection` row's `enabled` flag is the one switch that also changes graph behaviour (it disables the revise loop).

### Prompt inspection

`/dashboard/prompts`, `/dashboard/prompts/{name}` and `/dashboard/prompts/{name}/diff` browse the versioned prompt registry read-only, with a side-by-side line diff between versions; there is no edit endpoint (see [Prompt registry and versioning](../agent/prompt-registry.md)).

### Agent runs

`/dashboard/agent-runs` lists the 100 most recent `agent_runs` rows and shows 24-hour and 7-day rollups of turns, tokens, cost and nearest-rank p50/p95 latency computed from the repository's totals. `/dashboard/agent-runs/{run_id}` renders one turn as a **waterfall** of its `agent_run_steps`: node spans bracketing the LLM and tool steps inside them, the turn's span, cost by model, the tool calls, and the prompt-version snapshot the graph had active with a flag marking which prompts the steps could attribute (an unflagged prompt was active but not attributed, not unused). Because step recording stops at the per-turn cap and the dropped count is not persisted, a full page of steps is shown as possibly truncated. An unknown run id is a 404. These pages read only; the data model and how it is written are on [Observability, turn metrics and cost](../agent/observability-and-metrics.md).

## Operational notes

- Set both dashboard credentials in any deployment that is not `development`; leaving them unset does not expose the dashboard in production but does make it unreachable.
- Config edits are per agent and isolated; an invalid provider name is rejected at the service, and the repository also refuses a provider outside the catalog.
- The dashboard shares the request-scoped session and the JSON error envelope, so a domain error on a dashboard page returns the same envelope the API uses, with the `WWW-Authenticate` challenge preserved on a 401.
