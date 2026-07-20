# weather-trip-date-accuracy — Summary

Lane: high-risk
Confidence: high
Reason: Public-contract hard gate — `get_weather` / `get_packing` are re-exported to MCP clients via `app/mcp/server.py` (wraps `ALL_TOOLS`), so changing their signature and their beyond-horizon behavior is a client-visible contract change. Lane stays high-risk: the human narrowed the approach (E001 → option B, additive) but did not remove the contract touch. Confidence raised low → high once E001 resolved the design fork.
Flags: external systems, public contracts, existing behavior
Affects: `app/tools/weather_tools.py` (agent tool contract, MCP-exported), `app/services/weather_service.py`, `app/tools/registry.py` → `app/mcp/server.py`
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> merge PR và xử lý tiếp next issue liên quan đến thời tiết sai và giá vé bịa.
> note: sử dụng skill "/feature-intake" to start for new issue/ticket

Scope-deciding context from the preceding turns, in order:

> có, mở issue lần lượt cho từng cái

(referring to the findings from conversation `29c9de9c-df33-460f-9fb2-f255b55636a5`, filed as
MIN-66 / GitHub #97 and MIN-67 / GitHub #98)

MIN-66 / #97 — `get_weather` and `get_packing` have no date parameter, so they always return a
forecast starting today. The agent presented 20–22 Jul weather as the weather for a 1–3 Sep trip,
then built a "weather-fit" itinerary and packing list on it. `/destinations/{city}/climate` exists
as an API but is not exposed as an agent tool.

MIN-67 / #98 — the agent searched only the outbound leg, then quoted `$68 × 2 = $136` as a
"round-trip total". Tracked separately (see `specs/flight-fare-no-fabrication/`); this slug covers
the weather defect only.

## What changed

`get_weather` / `get_packing` accept an optional ISO `date`. Within the 15-day forecast horizon
the query narrows to that date; beyond it the service raises instead of silently returning
today's forecast — the silent fallback was the defect. A new `get_climate` tool exposes the
existing monthly-normals service as the correct answer for far-future dates, wired into the
planner and concierge domains (and therefore the MCP surface). The weather summary now names the
dates it actually covers, and concierge v11 / planner v10 require checking that range against the
dates being asked about.

### Rationale

Split from MIN-67 rather than bundled: different root causes (missing tool capability vs. model
inventing a number), different blast radius (MCP-exported contract vs. prompt), and different
lanes. Bundling would have forced the prompt-only fix through high-risk ceremony it does not need.

### Alternatives considered

- Bundle MIN-66 + MIN-67 into one slug — rejected; see Rationale.
- Treat as `normal` lane — rejected; the tool signature is re-exported to MCP clients, so the
  public-contract hard gate fires and cannot be self-downgraded.

### Deviations

- Rule 1 — The `get_climate` recovery pointer lived only in `DomainValidationError`'s `hint`,
  but agent tools raise `ToolException(str(e))` and `AppError.__str__` returns `detail` alone,
  so the pointer never reached the model at runtime. Moved into the detail; hint kept for the
  HTTP envelope. `apps/api/app/services/weather_service.py`. Commit `bf8e465`.
- Task 2.1 registered `get_climate` by adding `CLIMATE_TOOLS` to the `planner` / `concierge`
  entries in `TOOLS_BY_DOMAIN` rather than appending to `WEATHER_TOOLS` as the PLAN prose said.
  Same reachability, but keeps `climate_tools.py` outside that task's file ownership. Commit
  `5c921a5`.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| MCP re-exports the tool registry (public-contract gate) | `grep -n "ALL_TOOLS" apps/api/app/mcp/server.py` | 0 | `server.py:19` imports `ALL_TOOLS`; `:29` iterates it — tool signature is client-visible |
| Open-Meteo honours `start_date` in range, rejects beyond | `curl -s ".../forecast?...&start_date=2026-09-01&end_date=2026-09-03"` | 0 | in-range returns exactly the requested days; far date → `"Parameter 'start_date' is out of allowed range from 2026-04-18 to 2026-08-04"` — horizon is today+15, dynamic |
| Full backend suite | `DATABASE_URL=sqlite:///./travel.db pytest tests/agents tests/api/prompts tests/services tests/tools -q` | 0 | 503 passed; 2 `test_routing_tools.py` failures are pre-existing local `.env` artifacts (pass with `.env` aside) |
| Lint | `ruff check app tests/agents/test_weather_date_scope.py` | 0 | clean |
| `get_climate` reachable where intended | `python -c "from app.tools.registry import ALL_TOOLS, TOOLS_BY_DOMAIN; ..."` | 0 | `ALL_TOOLS` True, planner True, concierge True, budget False (by design) |
| Model-visible error names the alternative | `python -c "asyncio.run(weather_service.get_weather('Tokyo', date=today+45))"` | 0 | `str(e)` → "…beyond the 15-day weather forecast horizon. Call get_climate…" |
| Regression test actually bites | horizon check disabled → test fails; restored → passes | 0 | verified by the task agent; service left byte-identical |

### Rollback

- `git revert <sha>` (no migration; additive optional parameter + routing logic)
- Tool-contract revert if MCP clients break: restore the previous `get_weather` / `get_packing`
  signatures in `app/tools/weather_tools.py`; no registry or server change needed since both are
  registry-driven.

### Harness-Delta

- backlog — `gh issue create --label <name>` silently dropped the label when the active `gh`
  account lacked `AddLabelsToLabelable` permission: exit 0, URL returned, no warning. Cost a
  false "done" report. Worth a `/compound` entry: verify labels after `gh issue create`, and
  confirm the active `gh` account before any GitHub write.
