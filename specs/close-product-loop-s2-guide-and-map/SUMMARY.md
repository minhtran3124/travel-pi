# close-product-loop-s2-guide-and-map — Summary

Lane: normal
Confidence: high
Reason: three flags, no hard gate — existing-behavior (the chat Route panel is refactored to share its map), multi-domain (agent tool + backend registry + two web surfaces), and a widened MCP surface (a new read-only tool is auto-exposed). No auth, no migration, no HTTP route or response change, no external provider.
Flags: existing-behavior, multi-domain, mcp-surface
Affects: `app/tools/registry.py` (concierge domain), a new visa tool, `apps/web/src/components/chat/panel/RoutePanel.tsx`, the trip detail tab list, a new `/guide/[city]` route
Input-type: spec slice
Route: writing-plans → subagent-driven-development. No brainstorming (both open questions were decided by the user before intake); no xia2 (the sibling patterns were read during intake and are cited below).
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

Slice 2 of the approved umbrella `specs/close-product-loop/design.md`, whose §S2 reads:

> - `/guide/[city]`: three sections from `GET /visa`, `GET /tips`, `GET /destinations/climate?city=`,
>   with the visa disclaimer rendered verbatim from the API. Entry points: trip header
>   (destination city) and `/places`.
> - Trip detail **Map** tab: maplibre map with markers for trip places (`/trips/{id}/places`) and
>   itinerary items that have a `place_id`, coloured by day; click → item summary. Map component
>   is extracted from `RoutePanel` into `components/map/`. No routing lines in S2.

Two decisions the user made when asked, verbatim:

> - dung chung tab map
> - tao tool cho visa va bind vao concierge

The first settles a question raised at intake: share one map component between the chat Route panel
and the new tab, rather than writing a second map and leaving two to maintain. The second is an
addition beyond the umbrella design.

## What changed

Intake only — no code.

### Rationale

**The visa tool is the one piece of new scope, and it closes a real gap.** Visa is the only
destination-knowledge capability with a REST route and no agent tool: `GET /visa` exists
(`app/routers/visa.py:17`), but the registry's `concierge` domain carries places, weather, climate,
routing, tips, hotel search and knowledge — no visa (`app/tools/registry.py:52-61`). So the
chatbot can answer "what's the weather" and "any local tips" but not "do I need a visa", while the
same information sits one route away. Binding it to `concierge` puts it beside `get_local_tips`,
which is exactly where a traveller would expect it.

`app/tools/tip_tools.py` is the shape to copy, not a pattern to invent: a read-only lookup over a
DB-backed service, its own `session_scope`, domain errors mapped to `ToolException`, and no
side-panel artifact. The visa endpoint's own semantics carry over unchanged — either `city` or
`country`, fuzzy matched, an unknown location returns `found: false` rather than an error, and the
response carries a `disclaimer` the model must not paraphrase away.

**Sharing the map is the lower-risk option despite touching chat.** S1 proved the shape: the flight
and hotel result cards were lifted out of two chat panels into shared components, the eight panel
tests stayed green, and the diff was 6 insertions against 185 deletions. `RoutePanel.tsx` is 165
lines and already loads maplibre dynamically, so the piece that moves is small.

### Alternatives considered

- **Write a second map for the tab and leave `RoutePanel` alone.** Zero risk to the chat today, at
  the cost of two maps to keep in step forever. Rejected by the user ("dung chung tab map"), and S1
  showed the extraction is safe when the panel's tests pin its behaviour.
- **Leave visa REST-only and let `/guide/[city]` be its only surface.** That is what the umbrella
  design said. Rejected by the user: the gap is in the chatbot, which is now the product's main
  surface, and a page does not close it.
- **A `get_visa` tool on `planner` as well as `concierge`.** Not asked for. Planner is trip shaping;
  concierge is destination knowledge, and visa is knowledge.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| SUMMARY shape | `python .claude/scripts/verify_summary.py --lane close-product-loop-s2-guide-and-map` | 0 | intake-time check | |

### Not auto-verified

- **The MCP surface widens by one tool.** `TOOL_METADATA` marks everything outside `_DESTRUCTIVE`
  as `readOnly`, and `app/mcp/server.py` filters only the destructive four, so a new visa tool is
  auto-exposed over MCP the moment it is registered. Read-only and PII-free, so benign — but it is a
  surface change that no gate will announce, which is why it is written here. Reached traceability
  against `registry.py:76-95`; no diff exists yet to corroborate it.
- **Six tabs on the trip page.** Map makes it six, and the row will be tight on a narrow screen.
  Observed on the S1 UAT screenshots at 1280px, not measured below that.

### Rollback

- `git rm -r specs/close-product-loop-s2-guide-and-map` (intake artifacts only; no code yet)

### Harness-Delta

- none
