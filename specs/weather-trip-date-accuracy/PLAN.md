---
slug: weather-trip-date-accuracy
status: active
owner: Minh Tran
created: 2026-07-20
---

# Weather answers must match the trip's dates

## 1. Motivation

`get_weather` / `get_packing` always return a forecast starting **today**. Asked about a
1–3 Sep trip on 20 Jul, the agent reported the 20–22 Jul forecast as that trip's weather —
34°C, rain on 2 of 3 days — then built a "weather-fit" itinerary (indoor Day 2) and a packing
list (umbrella, waterproof) on top of it. All confidently stated, no caveat.

MIN-66 / GitHub #97. Evidence in `SUMMARY.md`; the design fork is resolved in `ESCALATIONS.md`
E001 (option B: keep `get_weather` forecast-only, add a separate `get_climate` tool).

## 2. Non-goals

- Per-day weather for far-future dates. `climate_service` returns **monthly normals**; there is
  no data source here that can give a per-day September forecast in July, and pretending
  otherwise would recreate the bug in a new shape.
- Changing `climate_service`, its router, or its response schema — all already exist and are
  tested (`tests/api/weather/test_climate.py`).
- The flight-fare fabrication (MIN-67 / #98) — separate slug.
- A climate side panel. `get_packing` already returns a plain dict with no panel; a panel is
  additive and not required to fix the defect.

## 3. Success Criteria

1. Asking for weather on a date beyond the forecast horizon can no longer silently return
   today's forecast — the tool refuses and names `get_climate` instead.
2. `get_climate` exposes the existing monthly-normals data to the agent.
3. `get_weather`'s summary states the dates it actually covers, so a date mismatch is visible
   to the model rather than invisible.
4. Existing MCP clients keep working: `get_weather` / `get_packing` gain only an **optional**
   parameter; `get_climate` is purely additive.

## 4. Tasks

### Task 1.1 — Thread an optional date through the weather service (wave 1)

- **Files:** apps/api/app/services/weather_service.py, apps/api/tests/services/test_weather_service_date.py
- **Action:** Add an optional `date: date | None = None` to `get_weather` and `get_packing`.
  When set, pass `start_date`/`end_date` to the Open-Meteo forecast call instead of bare
  `forecast_days` (the API supports it; `_fetch_json` at ~line 210-226 currently sends only
  `forecast_days`). When the requested date is beyond the forecast horizon, raise a domain
  error naming climate normals as the alternative — do NOT fall back to today's forecast.
  Define the horizon as a module constant, not a magic number. Keep `date=None` behaving
  exactly as today (regression safety for every existing caller).
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/services/test_weather_service_date.py tests/api/weather -q`
- **Done:** `date=None` path byte-identical to current behavior; an in-range date narrows the
  window; an out-of-range date raises rather than returning today.

### Task 1.2 — Add the `get_climate` agent tool (wave 1)

- **Files:** apps/api/app/tools/climate_tools.py, apps/api/tests/tools/test_climate_tools.py
- **Action:** New tool `get_climate(city: str, month: int | None = None)` wrapping
  `climate_service.get_climate`. Follow the `get_packing` shape exactly — hand-authored
  `GetClimateArgs(AppBaseModel)` with per-field descriptions, `@tool(args_schema=GetClimateArgs)`,
  `log_tool_call`, re-raise `UpstreamError`, wrap other `AppError` in `ToolException`, return
  `dump(...)`. No panel, no injected args. The docstring and field descriptions must make the
  forecast-vs-normals distinction explicit, since the model choosing wrong is the accepted
  residual risk of E001 option B.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/tools/test_climate_tools.py tests/tools/test_tool_registry.py -q`
- **Done:** Tool importable and invocable; passes the registry's parametrized
  `test_every_tool_has_explicit_described_schema`.

### Task 2.1 — Wire the tool into the registry and surface covered dates (wave 2)

- **Files:** apps/api/app/tools/weather_tools.py, apps/api/app/tools/registry.py, apps/api/tests/tools/test_weather_tools.py
- **Action:** Add the optional `date` to `GetWeatherArgs` / `GetPackingArgs` and pass it
  through to the service (schema descriptions must tell the model to use `get_climate` for
  far-future dates). Include the **actual covered dates** in the `get_weather` summary string
  so a mismatch is legible to the model. Register `get_climate` by appending it to
  `WEATHER_TOOLS`; confirm it lands in the `planner` and `concierge` domains and in `ALL_TOOLS`
  (and therefore the MCP surface) with no separate registration step.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/tools -q`
- **Done:** `get_climate` present in `ALL_TOOLS`; weather summary names its date range; no
  existing tool test regresses.

### Task 3.1 — Teach the prompts when to use climate vs forecast (wave 3)

- **Files:** apps/api/app/prompts/concierge/v11.md, apps/api/app/prompts/planner/v10.md, apps/api/app/prompts/active.yaml
- **Action:** Copy `concierge/v10.md` → `v11.md` and `planner/v9.md` → `v10.md` (never edit a
  shipped version in place), then add the rule: a date inside the forecast horizon uses
  `get_weather`; a date beyond it uses `get_climate` and must be described as typical/average
  conditions, never as a forecast. Extend the concierge `## Grounding (in order)` section and
  the `## Example — weather` block. Flip `active.yaml` `concierge: 10 → 11`, `planner: 9 → 10`.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/api/prompts tests/agents -q`
- **Done:** Both prompts describe the split; `active.yaml` points at existing files (guarded by
  the registry test rewritten in `a64c981`).

### Task 4.2 — Repair callers broken by the new signature (wave 4)

- **Files:** apps/api/tests/unit/test_weather_packing.py, apps/api/tests/prompts/test_active_versions_load.py
- **Action:** Added after the full suite (not the per-wave subsets) surfaced two regressions the
  wave verifies had missed. `get_packing` forwards `date=` unconditionally, which breaks five
  monkeypatched `_mock_get_weather(city, days=None)` fakes — widen the fakes to match the real
  signature rather than making production code conditional to accommodate test doubles.
  `test_min53_bumped_versions_active` hardcodes `concierge == 10` / `planner == 9`; update to
  11 / 10. See Risks — that test is a known tripwire, not fixed here.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest -q` (with `.env` moved aside)
- **Done:** Full suite green, not just the per-wave subsets.

### Task 4.1 — End-to-end regression for the reported scenario (wave 4)

- **Files:** apps/api/tests/agents/test_weather_date_scope.py
- **Action:** Cover the exact MIN-66 scenario: a far-future trip date must not yield a
  today-anchored forecast. Assert at the seam that is deterministic under `FakeLLM` — the
  service/tool refuses an out-of-horizon date and `get_climate` is the reachable alternative.
  Do not assert on model prose.
- **Verify:** `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/agents/test_weather_date_scope.py -q`
- **Done:** Test fails against the pre-fix behavior and passes after.

## 5. Risks

- **Model picks the wrong tool.** The accepted residual risk of E001 option B. Mitigated by
  explicit tool descriptions (1.2), prompt rules (3.1), and by 1.1 making the wrong call *fail
  loudly* instead of silently returning today — the failure mode degrades from "confident wrong
  answer" to "tool error the model must handle".
- **Public-contract gate.** `get_weather` / `get_packing` are re-exported to MCP via
  `app/mcp/server.py`. Changes are additive-optional, but the commit will trip
  `risk-corroboration.sh`; authorize with `RISK_WARN_CATEGORIES="public-contract"` and keep the
  high-risk lane declared in SUMMARY.md.
- **Open-Meteo `start_date` semantics.** Task 1.1 assumes the forecast endpoint honours
  `start_date`/`end_date` within its horizon. Verify against the live API before building 2.1
  on top of it; if it does not behave as assumed, 1.1's error path still holds the line.
- **Stale prompt in the running agent.** Prompt changes do not hot-reload (registry singleton +
  graph built at lifespan). Any manual check needs `docker exec api-api-1 touch app/main.py`.
- **Hardcoded prompt versions are a recurring tripwire.** `tests/prompts/test_active_versions_load.py::test_min53_bumped_versions_active`
  pins `concierge`/`planner`/`booking`/`memory_extraction` to literal numbers, so every legitimate
  prompt bump breaks it — its comment has grown into a changelog of past bumps. This is the second
  such test hit in two days (the first was rewritten in `a64c981`), and it is now redundant with
  both `test_every_active_version_loads_nonempty` directly above it and the rewritten
  `test_active_version_matches_active_yaml`. Bumped the numbers here to stay in scope; **recommend
  deleting it separately** rather than maintaining a third copy of the same guard.
- **Per-wave verify subsets missed real regressions.** Waves 1-3 each ran only their own test
  subset and passed; the full suite then failed on `tests/unit/` and `tests/prompts/`, neither of
  which any wave's verify command covered. Task 4.2 exists only because of that gap — a full-suite
  gate belongs at the end of any plan that changes a widely-called signature.

## 6. Status Log

- 2026-07-20 — Intake: high-risk (public-contract hard gate), confidence low → high after E001.
- 2026-07-20 — E001 decided by Minh Tran: option B (separate `get_climate`).
- 2026-07-20 — Plan written; branch `fix/weather-trip-date-accuracy` off `d3acd97`.
