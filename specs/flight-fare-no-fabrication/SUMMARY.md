# flight-fare-no-fabrication — Summary

Lane: high-risk
Confidence: high
Reason: Public-contract hard gate — `search_flights` is re-exported to MCP clients via `app/mcp/server.py` (wraps `ALL_TOOLS`), so adding a `return_date` parameter is a client-visible contract change. Direction is unambiguous once scope is chosen (E001), hence high confidence.
Flags: public contracts, existing behavior
Affects: `app/tools/flight_tools.py` (agent tool contract, MCP-exported), `app/services/flight_service.py`, `app/prompts/planner/*`
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> merge PR và xử lý tiếp next issue liên quan đến thời tiết sai và giá vé bịa.
> note: sử dụng skill "/feature-intake" to start for new issue/ticket

> có, mở issue lần lượt cho từng cái

MIN-67 / GitHub #98 — in conversation `29c9de9c-df33-460f-9fb2-f255b55636a5` the agent searched
only the outbound leg (`DAD → TYO`, 2026-09-01) and then told the traveller
"**from $136** round-trip total if you take the cheapest one each way" — `$68 × 2`. No return leg
was ever searched; the number came from no tool. It then fed the "$1,200–$2,200" budget ballpark.

### What changed

Intake only so far.

### Rationale

Split from MIN-66 (`specs/weather-trip-date-accuracy/`): different root cause and different
files, so bundling would have dragged a prompt-shaped fix through unrelated tool-contract work.

Corrected finding from the original issue: I first reported this as "no infrastructure gap — the
model simply invented a number". That was wrong. `GET /flights/search` **already** supports
`return_date` and returns `return_count` / `return_results` (`app/schemas/flight.py:79-132`), but
that capability was never wired into the LLM tool (`SearchFlightsArgs` is strictly one-way,
`app/tools/flight_tools.py:59-115`). The model had no correct call available. Correction posted to
GitHub #98.

Two contributing factors: the tool summary (`flight_tools.py:175-182`) never says "one-way" and
hardcodes `$` with no currency code, so the model has no textual cue what the fare covers; and the
`budget` sub-agent has no flight tool at all (`registry.py:56`), so it cannot verify a fare it is
asked to total.

### Alternatives considered

- Prompt-only fix (forbid derived totals, no tool change). Rejected as insufficient on its own:
  it would leave the agent unable to answer a legitimate round-trip question at all. Kept as one
  half of the fix.
- Bundle with MIN-66 — rejected; see Rationale.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| _pending implementation_ | | | |

### Rollback

- `git revert <sha>` — additive optional parameter + prompt version bump; no migration.
- Prompt-only revert: flip `active.yaml` `planner` back one version.

### Harness-Delta

- backlog — `AppError.__str__` returns `detail` only, so any `hint=` given to a domain error is
  silently dropped on the agent-tool path (`raise ToolException(str(e))`, used by every tool in
  the repo). Found while fixing MIN-66. Recovery hints written for the model may never reach it.
  Worth a `/compound` entry and a repo-wide look.
