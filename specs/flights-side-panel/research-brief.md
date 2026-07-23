# Research Brief — flights-side-panel

> **xia2 depth:** Standard. **PROJECT.md caveat:** the xia2 `PROJECT.md` is stale (it still
> describes the `harness-skills` meta-repo, not this FastAPI/Next.js app). Findings below are
> **not** from its guessed mappings — every claim is verified directly against travel-pi source
> (two Explore passes + a spec-review pass read `_base.py` / `panels.py` / `mapper.py` / the FE
> registry). Recommend bootstrapping a real PROJECT.md via `/bootstrap-xia2` separately; it does
> not block this feature.
>
> **Step 2.5 stop-condition applied:** `specs/agent-side-panel/RESEARCH.md` is the in-repo
> decision doc that already settled the `content_and_artifact` approach (and it shipped for
> route/weather/air_quality). Web upstream/docs research skipped per xia2 Step 2.5.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Reuse existing** — mirror the shipped side-panel pattern; add one `flights` kind |
| **Why this is the lightest credible path** | The BE mapper + FE stream/drawer already dispatch *any* panel `kind`; work is one tool conversion + one Pydantic projection + one FE component + registry/type entries |
| **Confidence** | 92% |
| **Next step** | Invoke `writing-plans` to turn `design.md` into a waved PLAN.md |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | Monorepo (pnpm + Turborepo): `apps/api` FastAPI backend, `apps/web` Next.js frontend |
| Primary language + runtime | Python 3.13 (local) / 3.12 (Docker); Node 24 (web) |
| Frameworks / platforms | FastAPI `>=0.110,<0.137`; Pydantic v2 `>=2.6,<3`; LangChain `1.x`; LangGraph `1.x`; Next.js `16.2.9`; React `19.2.4`; TS `^5` |
| Relevant packages | `langchain` (tool `response_format="content_and_artifact"`), `langgraph` (ToolNode/mapper), Pydantic v2 (`AppBaseModel`) |
| Detectable versions | `apps/api/requirements.txt`, `apps/api/requirements-ai.txt`, `apps/web/package.json` |
| Important constraints | ORM confined to repositories; services raise domain exceptions; tests on `FakeLLM` (no network); `datetime.now(timezone.utc)`; commit `add`/`commit` as separate steps |

## Feature Understanding and Assumptions

- **Requested feature:** render `search_flights` results as a compact-list panel in the existing
  chat side-drawer (flights only this iteration).
- **Success:** after a flight search, a "Flights" tab appears in the drawer showing every result
  as a dense row (click to expand); the model context stays lean (summary only).
- **Assumptions from the request (all user-approved in `design.md` §3):** compact list layout;
  static + row-expand (no client sort); read-only (no Book); empty/error → no panel (chat text).
- **Assumptions still needing confirmation:** none material — design was reviewed + approved.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `_base.py:93` `panel_result(summary, *, kind, data)` helper for `content_and_artifact` tools |
| `Local` | `mapper.py:158-164` reads `ToolMessage.artifact` → `events.panel(kind, data)`; dispatches **any** kind (no change needed) |
| `Local` | `panels.py:24` `PanelKind` literal + per-kind Pydantic models (`RoutePanel`/`WeatherPanel`/`AirQualityPanel`) with `from_*_response()` |
| `Local` | FE `panel/registry.ts:20` `PANEL_RENDERERS` + `PANEL_LABELS`; `SidePanel.tsx` tabs/auto-show/replace-by-kind; `useAgentStream.ts` `upsertPanelByKind`; `lib/stream/panel.ts:9` FE `PanelKind` union |
| `Local` | `schemas/flight.py` `Flight` + `Airline` — real fields only (no aircraft/baggage/layover) |
| `Local` | `tests/tools/test_routing_tools.py:35` — ToolCall-invoke → `ToolMessage.artifact` test pattern to copy |
| `Local (decision)` | `specs/agent-side-panel/RESEARCH.md` + `SUMMARY.md` — `content_and_artifact` chosen as the doc-correct rich-UI channel; `Command(update=...)` and custom `get_stream_writer` rejected |
| `Inference` | `content_and_artifact` on `search_flights` breaks 3 existing `test_booking_tools.py` tests (list/price-sort/no-match) — must be updated (verified by spec review) |

## Local Findings

- **Reusable extension points:** `panel_result()` (BE), the mapper (no change), `SidePanel` +
  `upsertPanelByKind` (FE, no change). Adding a kind is additive at 4 spots only.
- **Conventions to preserve:** one Pydantic model per kind + `from_*_response()` classmethod;
  FE component is pure render (`{ data }`), no network/state beyond local expand; keep the LLM
  `summary` short (artifact carries detail).
- **What can be reused:** ~90% — the entire transport (SSE `panel` event), drawer, tab logic,
  replace-by-kind, history rehydration off `ToolMessage.artifact`.
- **What's missing locally:** a `FlightsPanel` Pydantic model + `"flights"` in both `PanelKind`
  literals; a `FlightsPanel.tsx` component + registry/label/type entries; the tool conversion.

## Upstream Findings

Skipped (xia2 Step 2.5): the in-repo decision doc `specs/agent-side-panel/RESEARCH.md` already
did this research and the pattern shipped. `content_and_artifact` is a stable LangChain 1.x tool
feature, already used by `routing_tools`/`weather_tools` in this repo.

## Docs Findings

Skipped per Step 2.5 (settled by local decision doc + shipped usage). No version risk:
LangChain 1.x `response_format="content_and_artifact"` is exactly what the existing panel tools
use; no deprecation in scope.

## Recommendation

- **Primary:** **Reuse existing** — clone the route/weather panel pattern for `flights`.
- **Why lightest credible:** transport + drawer are kind-agnostic and already shipped; the
  net-new surface is one projection model + one FE component + registry/type/kind entries + the
  tool conversion. No new dependency, no schema/migration, no mapper/drawer change.
- **Why next-best lost:** *building a bespoke flights rendering path* (e.g. custom SSE event or
  embedding data in chat markdown) was rejected in `agent-side-panel/RESEARCH.md` — duplicates
  transport, bloats model context, and breaks history rehydration.
- **What would change this:** if flights needed live interactivity (server round-trips on
  sort/filter) the read-only artifact model wouldn't suffice — but design §2 explicitly scopes
  that out.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:** the tool conversion breaks **3** existing `test_booking_tools.py` tests
  (documented in `design.md` §5.1/§6) — the plan must update all three and re-home the sort-order
  assertion onto the artifact. Public-contract-additive commit may trip `risk-corroboration.sh`
  → authorize with `RISK_WARN_CATEGORIES="public-contract"`.
- **Evidence gaps:** none blocking; pattern is code-verified.
- **Version uncertainties:** none.
- **Follow-up questions:** none — design approved.

## Source Pack

- **Local files read:** `apps/api/app/tools/_base.py`, `app/tools/flight_tools.py`,
  `app/streaming/mapper.py`, `app/streaming/panels.py`, `app/schemas/flight.py`,
  `apps/web/src/components/chat/panel/registry.ts`, `SidePanel.tsx`, `useAgentStream.ts`,
  `lib/stream/panel.ts`, `specs/agent-side-panel/{RESEARCH,SUMMARY,PLAN}.md`, manifests.
- **Upstream/official:** none (Step 2.5 stop-condition).

## Evidence Boundary

> **Confirmed from artifacts:** the panel pipeline shape + all four extension points; the real
> `Flight`/`Airline` schema fields; the ToolCall-invoke test pattern; the 3 tests broken by the
> conversion; `content_and_artifact` already in production use here.
> **Inferred from patterns:** exact projection code for `FlightsPanel.from_flights` (mirrors
> `from_*_response`); FE row/expand markup (design-level, not yet written).
> **Not checked:** external LangChain web docs (deliberately — settled by local decision doc);
> the stale xia2 `PROJECT.md` mappings (bypassed in favour of direct code reads).
