---
problem_type: decision
module: agent/i18n
tags: langgraph, i18n, side-panel, streaming, next-intl, structured-output, deterministic-over-llm, injected-state
severity: standard
applicable_when: Localizing agent-produced content (chat side panel) to the user's detected conversation language across the LangGraph agent → SSE stream → Next.js frontend.
affects:
  - apps/api/app/agents/supervisor.py
  - apps/api/app/agents/state.py
  - apps/api/app/prompts/supervisor/v5.md
  - apps/api/app/streaming/panel_localizer.py
  - apps/api/app/streaming/mapper.py
  - apps/api/app/agents/graph.py
  - apps/api/app/streaming/events.py
  - apps/web/src/components/chat/panel/PanelIntlProvider.tsx
  - apps/web/src/components/chat/useAgentStream.ts
  - apps/web/src/lib/stream/parseSSE.ts
supersedes: null
confidence: high
confirmed_at: 2026-07-08
---

## Applicable When

Localizing agent-produced content (here: the chat side panel) to the user's detected
conversation language, end to end across the LangGraph agent, the SSE stream, and the
Next.js frontend. MIN-57.

## Decision 1

### Context
The side panel must render in the traveller's language, needing a per-turn language signal.
The supervisor LLM already ran a structured-output `SupervisorIntent` whose `language` field
was computed every turn but **discarded**.

### Options Considered
1. Reuse the supervisor's existing `SupervisorIntent.language` (already computed, thrown away).
2. Add a new deterministic library detector (lingua / langdetect) at the router/mapper.

### Decision & Rationale
REUSE the supervisor field. No new dependency; the detected code shares lineage with the LLM
that already chooses the reply language, so panel language and reply language stay consistent.
Persisted via `Command(update={"language": ...})` with an empty-code `or` fallback
(`lang = intent.language or state.get("language", "en")`) that never *pins* the language — a
genuine model-reported switch still flows through. Made conversation-level and **sticky** by
feeding the prior `state["language"]` back into the router prompt ("Established conversation
language: X; keep it unless the traveller clearly switches") and hardening the field
description to ignore lone interjections/loanwords ("ok"/"fine"). The library detector was
kept as a documented fallback, not built.

### Applicable When
You need a language/intent signal and an upstream LLM already produces structured output each
turn — harvest the discarded field before bolting on a parallel detector.

### Consequences
Zero new deps and single lineage, at the cost of trusting the LLM's self-report (mitigated by
stickiness + prompt guardrails). First turn seeds `"unknown"`; default `"en"` where absent.
Complements [[reflection-humanmessage-language-flip-decisions]] (deterministic-leaning
correction layered on the existing LLM detector).

## Decision 2

### Context
Panel `data` dicts carry English strings baked in by the panel projections (weather WMO
descriptions, AQI category + advice, place category, hotel amenities, and a free-form place
`description`). These need Vietnamese output when the conversation is `vi`. The strings are
static/seeded — there are **no** locale-aware providers to switch.

### Options Considered
1. LLM-translate the entire payload.
2. Deterministic lookup tables for everything.
3. Hybrid — deterministic tables for bounded strings, LLM only for the free-form field.

### Decision & Rationale
HYBRID. Bounded enum-like strings get module-level `vi` lookup tables (`WEATHER_VI`,
`AQI_CATEGORY_VI`, `AQI_ADVICE_VI`, `CATEGORY_VI`, `AMENITY_VI`), each **parity-tested**
against its backend source of truth — stable, offline-safe, FakeLLM-friendly, no network.
Only the one genuinely free-form field (place `description`) goes through an injected async
translator. Mirrors the existing `resolve_category` "deterministic backend over LLM-reliance"
precedent. `en`/non-`vi` is a strict identity no-op (same object, un-copied); `vi` deep-copies
first so the persisted checkpoint's English payload is never mutated in place.

### Applicable When
Localizing a payload that mixes a closed set of enum-like strings with a little free text —
table the bounded part, LLM only the unbounded part.

### Consequences
Lookup tables must stay in sync with their backend sources (enforced by parity tests). The
translator is injected, never a direct `get_fast_llm()` call, so an absent translator degrades
to the English description rather than failing. See [[inject-llm-handle-for-streaming-layer]].

## Decision 3

### Context
Localization needs a single insertion point in the agent→SSE path. Panels originate as tool
artifacts (built at tool-execution time), then become `panel` events at the mapper.

### Options Considered
1. Localize at the mapper/emission seam (`stream_agent_events`), where artifacts become events.
2. Localize inside each tool via `InjectedState` (each tool localizes its own artifact).

### Decision & Rationale
MAPPER SEAM. One place owns localization; every tool stays untouched. Avoids the known
`InjectedState`/`args_schema` injection pitfall (memory `explicit-args-schema-breaks-langgraph-injection`).
The mapper captures `current_language` the moment a node persists it (`delta.get("language")`),
seeds it best-effort from `graph.aget_state(cfg)` **before** the astream loop so a HITL-resume
turn (which skips the supervisor and emits no language delta) still tags its panels/done, and
passes it to `localize_panel` at emission. Ordering is safe: the supervisor runs before any
sub-agent tool, so its state-update delta streams before the first panel.

### Applicable When
A cross-cutting transform must touch many producers uniformly — apply it at the shared
emission/mapping boundary, not by threading state into each producer.

### Consequences
Tools stay localization-agnostic; localization is centralized and testable. The mapper gains a
language-tracking concern + a best-effort pre-seed (try/except, default `en`) for the resume
path, and a second `aget_state` read per stream.

## Decision 4

### Context
The FE already has a next-intl UI locale from a cookie. Panel content is localized by the
backend to the LLM-detected conversation language, which can diverge from the cookie.

### Options Considered
1. Render the panel from the next-intl UI cookie locale (reuse ambient app locale).
2. Follow the detected typed language streamed from the backend on `panel`/`done` SSE events.

### Decision & Rationale
Follow the DETECTED typed language, streamed on both `panel` and `done` events (a `language`
field added to each event contract — an additive superset). `useAgentStream` carries it as
`panelLanguage` (default `"en"`, updated only when an event supplies a code; `applyPanelLanguage`
shared across the send/resume/retry handlers). The panel subtree is wrapped in a nested
`NextIntlClientProvider` (`PanelIntlProvider`) keyed off that streamed language — NOT the
cookie — handing only the `Panel` message slice. This keeps static panel labels consistent
with the backend-localized dynamic content (both reflect the same detected language).

### Applicable When
A UI subtree's language must match server-produced content whose language is determined
server-side — override the ambient locale for just that subtree with a nested provider keyed
off the server signal, rather than assuming the global UI locale.

### Consequences
Labels and data always agree, at the cost of a second (nested) intl provider and a new field
on the `panel`/`done` SSE contract. The static JSON import in `PanelIntlProvider` adds some
client bundle weight (whole catalogs, only the `Panel` slice passed to the provider) —
acceptable at 2 locales. A resume/retry turn with no `language` leaves the last value intact.

## Related

- docs/solutions/agent/reflection-humanmessage-language-flip-decisions.md
- docs/solutions/streaming/inject-llm-handle-for-streaming-layer.md
