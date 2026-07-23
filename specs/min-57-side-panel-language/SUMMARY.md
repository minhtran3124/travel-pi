# min-57-side-panel-language — Summary

Lane: high-risk
Confidence: high
Reason: Full-stack fix chosen (static-label i18n + backend locale plumbing + LLM translation of dynamic panel content following the detected typed language) trips 5 flags incl. public contract (new ChatRequest locale/language) and multi-domain.
Flags: external-systems, public-contracts, existing-behavior, weak-proof, multi-domain
Affects: ChatRequest schema (apps/web + apps/api), agent stream/panels contract (app/streaming/panels.py, lib/stream/panel.ts), side-panel renderers (apps/web/src/components/chat/panel/*)
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- Verbatim intake oracle for /intent-review. Combines the Linear issue MIN-57 body
     with the two scope decisions the user made at intake. -->

From Linear MIN-57 (Bug: Side panel still returns English when the user asks in Vietnamese):

> ## Problem
> When the user chats in Vietnamese, the main chat response is already in the correct language, but the **side panel** (supplementary information, hotel/flight details, suggestions, etc.) is still displayed in English → an inconsistent language experience.
>
> ## Suspected causes (need further investigation)
> * The side panel may be pulling data directly from mock data / the backend API (which is in English) without going through the translate/re-generate step via the LLM the way the main chat does.
> * There may be missing logic to detect the user's language and pass it down to the side panel component.
> * The side panel may be rendering hardcoded labels in English instead of following the locale.
>
> ## Proposed solutions (to be evaluated — pick the appropriate approach)
> 1. **Pass the current conversation language** (detected from the user's input) down to the side panel component, so the side panel uses the correct locale for static labels (e.g. "Price" → "Giá").
> 2. For dynamic content pulled from the backend (hotel names, descriptions, etc.), consider:
>    * Translating via the LLM before displaying it in the side panel (keep proper nouns intact, translate only the descriptive parts).
>    * Or normalizing the backend to return data by locale if the data supports multiple languages.
> 3. Add i18n for the static labels in the side panel (use key-value pairs per language instead of hardcoding).
>
> ## To do
> * Investigate the side panel's current data flow (data source, whether it passes through the LLM or not).
> * Identify the list of static labels that need i18n.
> * Implement language detection + pass the language down to the side panel.
> * Test cases: user asks entirely in Vietnamese throughout the conversation; user switches language mid-conversation.

Scope decisions confirmed by the user at intake:

- **Scope = Full language consistency.** Fix BOTH (a) the hardcoded static labels in the panel renderers (via existing next-intl) AND (b) the dynamic backend content (hotel/weather descriptions, AQI advice, amenity/category names) — plumb a locale into `ChatRequest` → agent → `panels.py` and LLM-translate the descriptive text while keeping proper nouns intact.
- **Language signal = Detected typed language.** The side panel follows the language the user actually typed (as the chat reply does), NOT the UI locale cookie — even if the UI toggle is set to English.

## What changed

The chat side panel now renders in the conversation's dominant language. Backend: the
supervisor's already-computed `SupervisorIntent.language` is persisted into
`TravelAgentState.language` (empty-code fallback keeps the prior language, so a lone
"ok"/"fine" doesn't flip it; conversation-level guidance added to the supervisor prompt);
`app/streaming/mapper.py` seeds the language (incl. HITL-resume via a pre-loop `aget_state`),
tracks it from supervisor deltas, and localizes each panel at emission via the new async
`app/streaming/panel_localizer.py` — deterministic `vi` lookup tables for bounded strings
(weather/AQI/category/amenities) plus an injected `graph.translate_llm` (async, translate-to-
Vietnamese prompt) for place descriptions; `panel`/`done` SSE events gain a `language` field.
Frontend: `parseSSE`/`useAgentStream` carry the streamed language as `panelLanguage`, and a new
`PanelIntlProvider` wraps the panel subtree in a nested `NextIntlClientProvider` keyed off it,
with a new `Panel` message namespace (en+vi) the panel components consume via `useTranslations`.
The English path is a behavioral no-op (identity localization + additive `language` key).

### Rationale

Bug is caused by two independent string sources: (a) hardcoded English labels in `apps/web/src/components/chat/panel/registry.ts` + each panel renderer, which bypass the existing next-intl infra; and (b) dynamic content served English from the agent SSE `panel` stream (`app/streaming/panels.py`), because `ChatRequest` carries no locale and the backend is never told the language. The user chose full consistency over a frontend-only quick fix, accepting the higher-risk backend plumbing.

### Alternatives considered

- **Static-labels-only (frontend, normal lane)** — wire panel renderers to next-intl, leave dynamic content English. Rejected by user: leaves descriptions in English, partial fix.
- **Static now / dynamic later (phased)** — ship FE fix, open a follow-up issue for backend translation. Rejected by user in favor of doing both now.
- **Follow the UI locale cookie** instead of detected typed language. Rejected: chat reply already follows typed language; cookie would desync panel from the actual conversation language.

### Deviations

- Rule 1 — Task 2.1 edited the active supervisor prompt at `apps/api/app/prompts/supervisor/v5.md` (the version `registry.get("supervisor")` actually returns) instead of the planned `active.yaml`, which is only a name→version map (editing it would break the map and have zero prompt effect). High-blast `active.yaml` was left untouched. Commit `eb36ee5`. (PLAN file-manifest gap: `active.yaml` is a pointer, not prose.)
- Rule 1 — Wave 3 fixed 3 shape assertions in `apps/api/tests/api/agent/test_stream_events.py` (`==` on the exact panel/done payload) to include the additive `"language": "en"`; broken by the Wave-1 events.py superset but missed because Wave-1's verify didn't run `tests/api/agent/`. Shared-test-contract file added to Task 1.2 `<files>`. Commit `90a9269`. (wave-shared-file-partition.)
- Rule 3 — Task 4.2 also edited `apps/web/src/lib/stream/parseSSE.ts` (not in the original plan `<files>`) — the panel/done SSE envelope + parser actually live there; a type-only change would leave `language` undefined at runtime. Sanctioned by the task action ("if the envelope lives elsewhere, add it there"). Added to Task 4.2 `<files>`. (PLAN file-manifest gap.)

### Advisory Findings

<!-- Sub-threshold (score <80) correctness-review candidates: recorded, not blocking. -->

- **`.content` assumed `str`** (`app/streaming/mapper.py:117`) — the async translator returns `resp.content`; a provider returning content-blocks (list) would put a non-str into `place["description"]`. Consistent with the existing repo convention (`app/memory/extractor.py:122`, `app/agents/nodes.py:149` read `.content` identically) — a pre-existing whole-repo assumption, not introduced here. Advisory.
- **`locale={language}` passthrough** (`PanelIntlProvider.tsx`) — an out-of-range language code would reach `Intl` number formatting (ICU `#`) and could throw; the backend only emits validated `en`/`vi`, so unreachable today. Advisory.
- **Mixed-source language edge** (`useAgentStream.ts`) — if a `panel` event omits `language` but `done` supplies it, an artifact's `.language` can differ from the drawer's `panelLanguage`; low risk since the BE emits both together. Advisory.
- **Perf (non-correctness):** `localize_panel` awaits the translator per place (serialized N LLM calls) and the mapper does two `aget_state` reads per stream; the design's `(text, language)` cache was deferred. Acceptable at current scale.

### Verify

<!-- Filled during execution. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| BE streaming | `cd apps/api && ../../.venv/bin/python -m pytest tests/streaming -x` | 0 | incl. panel_localizer, mapper_language, panel_language_e2e |
| BE agents | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents -x` | 0 | incl. supervisor_language, graph_translate_handle (117) |
| BE event-shape | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_stream_events.py -x` | 0 | superset assertions updated |
| BE combined | `cd apps/api && ../../.venv/bin/python -m pytest tests/streaming tests/agents -x` | 0 | 144 passed |
| FE typecheck+lint | `cd apps/web && pnpm --filter web exec tsc --noEmit && pnpm --filter web lint` | 0 | Node v24 |
| FE unit | `cd apps/web && pnpm --filter web test` | 0 | 80 passed |
| FE prod build | `cd apps/web && pnpm --filter web build` | 0 | 12 static pages generated |
| BE full raw suite | `cd apps/api && make test` | 1 | **Env-limited**: 544 sqlalchemy conn errors (Postgres down + `.env` DATABASE_URL); flat across all waves → not a regression. Run `make test-docker` (Postgres) as the pre-merge cross-engine gate. |

### Rollback

<!-- Required (high-risk lane). Populate with exact undo commands once branch/commits exist. -->

- Revert code: `git revert <sha>` for each implementation commit
- Revert `ChatRequest` schema change: covered by the code revert (no DB migration if locale stays request-only; if a migration is added, `alembic downgrade -1`)

### Harness-Delta

- none
