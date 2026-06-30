# Local-tip agent tool — Intake Summary

Lane: normal
Confidence: high
Reason: Additive agent tool wrapping the already-existing TipService/router/DB; flags public-contract (new tool surfaced in /agent/manifest + MCP) and existing-behavior (concierge toolset changes additively). No hard gate fired — no schema change, no security surface, no external provider, no validation weakening, not a harness high-blast file.
Flags: public-contract (additive), existing-behavior (additive)
Affects: app/tools/registry.py (ALL_TOOLS / TOOLS_BY_DOMAIN → /agent/manifest + MCP tool list); concierge sub-agent toolset
Input-type: Change request
Route: in-place branch off v3 → implement + test + two-stage review (notify-and-proceed; no human gate — high confidence)
Escalate: no

## Intent

User request, verbatim (across turns, scope-deciding sentences in order):

> hãy tạo local-tip tool và provide cho agent phù hợp, tool này ko cần panel

> check trong code truoc, db backend đã sẵn có rồi, có service + router luôn rồi

Interpretation: the full local-tips stack already exists (`app/db/models/tip.py`,
`app/repositories/tip.py`, `app/services/tip_service.py`, `app/routers/tips.py`,
`app/schemas/tip.py`, `app/data/tips.py`). The work is **only** to expose it to the
agent as a LangChain `@tool` that wraps `TipService.get_tips(...)`, register it, and
bind it to the appropriate sub-agent. "ko cần panel" = plain `@tool` returning text
(NOT `response_format="content_and_artifact"` / `panel_result`; no FE side-panel).

## Rationale

- `TipService.get_tips(city|country|category|essential_only)` is the agent-facing
  lookup (`get_all_tips` is a dashboard-only flat view → not exposed to the agent).
- "Agent phù hợp" → **concierge**: it is the local-info specialist (already binds
  place + weather + RAG + routing tools). Local tips belong with it.
- Follows the established service-wrapping tool pattern (`place_tools.py`):
  `@tool` → `session_scope()` → `TipService(s).get_tips(...)` → `dump(...)`,
  mapping `AppError` → `ToolException` for self-correction.
- Read-only tool → no change to registry `_WRITE` / `_DESTRUCTIVE` sets;
  `TOOL_METADATA` will mark it `readOnly: true, destructive: false` automatically.

## Alternatives considered

- **DB-backed seed table from scratch** — rejected: the table/service/seed already
  exist (would have been a migration hard gate → high-risk; not applicable here).
- **Reuse RAG / LLM knowledge instead of a tool** — rejected: contradicts the
  explicit "tạo local-tip tool" ask and ignores the curated seed data.
- **Bind to planner (or both)** — deferred: concierge is the natural single home;
  can extend `TOOLS_BY_DOMAIN["planner"]` later if itinerary planning needs tips.

## Assumptions (stated; proceeding autonomously)

- Tool name `get_local_tips`; args mirror the service: `city`, `country`,
  `category`, `essential_only` (all optional; require at least one of city/country
  like the router does).
- Bound to **concierge** only.
- New file `app/tools/tip_tools.py` (`TIP_TOOLS`), wired into `registry.py`;
  unit test added. ≤3 files, additive → no full PLAN.md needed.

## Status: implemented

Files: `app/tools/tip_tools.py` (new `get_local_tips` + `TIP_TOOLS`),
`app/tools/registry.py` (import + bind to concierge),
`tests/tools/test_tip_tools.py` (new). Bound to **concierge** only.

## Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| tool + registry tests | `../../.venv/bin/python -m pytest tests/tools/test_tip_tools.py tests/tools/test_tool_registry.py -q` | 0 | 12 passed |
| lint | `../../.venv/bin/ruff check app/tools/tip_tools.py app/tools/registry.py tests/tools/test_tip_tools.py` | 0 | All checks passed |

## Rollback

- Revert code: `git revert <sha>` (additive — new tool file + 2 registry lines + test).
