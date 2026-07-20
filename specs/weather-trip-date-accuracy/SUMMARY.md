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

Nothing yet — intake only. Work is blocked pending the design decision recorded in
`ESCALATIONS.md`.

### Rationale

Split from MIN-67 rather than bundled: different root causes (missing tool capability vs. model
inventing a number), different blast radius (MCP-exported contract vs. prompt), and different
lanes. Bundling would have forced the prompt-only fix through high-risk ceremony it does not need.

### Alternatives considered

- Bundle MIN-66 + MIN-67 into one slug — rejected; see Rationale.
- Treat as `normal` lane — rejected; the tool signature is re-exported to MCP clients, so the
  public-contract hard gate fires and cannot be self-downgraded.

### Deviations

- none

### Verify

<!-- Populated during implementation. Intake ran no behavioral checks; the two facts below
     are the evidence the lane rests on. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| MCP re-exports the tool registry (public-contract gate) | `grep -n "ALL_TOOLS" apps/api/app/mcp/server.py` | 0 | `server.py:19` imports `ALL_TOOLS`; `:29` iterates it — tool signature is client-visible |
| Weather tools have existing test coverage (proof strength) | `ls apps/api/tests/tools/test_weather_tools.py apps/api/tests/api/weather/test_climate.py` | 0 | both exist; climate endpoint already covered |

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
