---
slug: min-57-side-panel-language
status: proposed
owner: Minh Tran
created: 2026-07-08
linear: MIN-57
---

# Side-panel language consistency (Vietnamese)

## 1. Problem

When a user chats in Vietnamese, the main chat reply is already Vietnamese (the LLM
mirrors the traveller's latest message), but the **side panel** — weather, air quality,
routes, flights, hotels, places — still renders in English. Two independent string
sources cause this:

1. **Static UI labels** are hardcoded English literals in the panel renderers
   (`apps/web/src/components/chat/panel/registry.ts` `PANEL_LABELS`, and literals inside
   `HotelsPanel.tsx` etc.: "night(s)", "Guest rating", "Amenities", "Nightly rate"…).
   The app already runs `next-intl`, but the `panel/*` subtree was never migrated to it
   (the `i18n-vietnamese` work migrated the chat *shell* only).
2. **Dynamic content** streamed from the backend (`panel` SSE events built in
   `apps/api/app/streaming/panels.py`) is static English: weather descriptions
   (`WMO_CODES`), AQI category/advice (fixed dicts), place category, hotel amenities, and
   free-form place `description` prose seeded in `app/data/`. Note: only the **places**
   panel payload (`PlacesPanelPlace`, `panels.py:537`) carries a free-form `description`;
   the **hotels** panel projection (`HotelsPanelHotel`) exposes no description field — its
   only localizable surface is the bounded `amenities` list (hotel names are proper nouns).

## 2. Goals

- The side panel renders in the **dominant language of the conversation** (see §6.1),
  consistent with the chat reply — even if the UI locale toggle is English, and without
  flipping on a lone language-neutral interjection ("ok", "fine").
- Both static labels **and** dynamic content are localized, including free-form
  place descriptions (hotel amenities are covered via the bounded lookup table; hotels
  carry no free-form description in the panel — see §1/§7).
- Language switches mid-conversation are honored (re-detected each normal turn).

## 3. Non-goals

- No UI-locale-cookie coupling: the panel follows the detected typed language, not the
  `next-intl` switcher. (The switcher continues to drive the rest of the app shell.)
- No new `ChatRequest` field — detection is fully backend-side (see §5).
- No third language. `en` + `vi` only, reusing the existing catalogs.
- No change to the deterministic flight/hotel seed algorithm, panel *kinds*, or the REST
  API shape. Only the SSE `panel`/`done` event payloads gain a `language` field.
- No new language-detection dependency — we reuse the supervisor's existing detection.

## 4. Success criteria

1. User chats entirely in Vietnamese → every side-panel string (labels + weather/AQI/
   category/amenities + place descriptions) renders Vietnamese.
2. User switches language mid-conversation → subsequent panels follow the new language.
3. `language == "en"` path is byte-identical to today (regression-proven).
4. Backend tests run offline (no real LLM); translator is injected, `FakeLLM`-safe.
5. `apps/api` suite + `apps/web` `tsc`/`lint`/`build` pass.

## 5. Architecture & data flow

One language signal, produced once, consumed in three places:

```
supervisor (LLM)  ──detects──►  intent.language ("vi")   [already computed today]
      │ persist (supervisor.py Command update)
      ▼
TravelAgentState.language   ──(sticky in checkpoint across turns)
      │  streamed as an "updates" delta
      ▼
streaming/mapper.py  ── tracks current_language ──►
      ├─ localizes each `panel` event's data   (server-side, §7)
      └─ tags `panel` + `done` events with language (to the FE, §8)
      ▼
apps/web  panel/* components:
      ├─ dynamic content: already-localized (rendered as-is)
      └─ static labels:   next-intl keyed off the STREAMED language (not the cookie)
```

**Key seam facts (from investigation):**

- `SupervisorIntent.language` (`apps/api/app/agents/supervisor.py:37`) is **already
  detected** every turn via structured output, but discarded — line 84 only persists
  `current_flow`. Reusing it means zero new detection code or dependency, and it shares
  the same LLM judgment that decides the reply language.
- Panels are built in English at **tool-execution** time and emitted at
  `streaming/mapper.py:164` from `ToolMessage.artifact`. The supervisor runs *before* any
  sub-agent tool, so `current_language` is always known before the first panel event.
- Dynamic panel text is **not** from live providers (Open-Meteo/ORS return numbers) and
  **not** LLM-generated — it is static English from seeded DB data + local lookup tables.
  So "locale-aware providers" is not applicable; localization is our own responsibility.

## 6. Backend — language capture

- Add `language: str` (default `"en"`) to `TravelAgentState` (`app/agents/state.py`).
- In `supervisor.py`, persist the already-computed value on the routing command:
  `Command(update={"current_flow": target, "language": intent.language}, goto=next_node)`.
- Sticky by design: HITL-resume turns that skip the supervisor keep the last-known
  language from the checkpoint.

### 6.1 Conversation-level (not latest-message) detection

The detected language must reflect the **dominant language of the whole conversation**,
not just the traveller's latest message. Vietnamese speakers routinely drop in short,
language-neutral English interjections and loanwords ("ok", "fine", "good", "sure"); a
lone such turn must **not** flip the panel to English (which would re-create the very
reply/panel divergence this fix targets, since the LLM reply — being context-aware —
stays Vietnamese).

Two mechanisms, no new plumbing (the supervisor already receives the full history +
summary via `system_with_summary(state, system), *state["messages"]`):

1. **Refine the supervisor prompt + `SupervisorIntent.language` field guidance** to
   instruct: detect the traveller's *primary/dominant* language across the entire
   conversation; ignore short interjections, loanwords, and language-neutral tokens; only
   report a different code on a clear, sustained switch.
2. **Stickiness / hysteresis:** feed the previous turn's `state["language"]` into the
   supervisor's context (a line in `system_with_summary` or the supervisor system prompt:
   "the established conversation language is `<X>`; keep it unless the traveller clearly
   switches"). The default outcome is "keep the established language", so a single
   ambiguous/English-interjection turn cannot flip it.

**Consistency invariant:** the panel language should track the *reply* language. The reply
is LLM-emergent and context-aware, so it does not flip on a lone "ok"; conversation-level
sticky detection keeps the panel aligned with it far better than latest-message detection
would. (The reply-language rule in `communication_style` is unchanged — it already benefits
from the LLM's full-context awareness; we are only making the *panel* signal equally robust.)

## 7. Backend — localization at the emission seam

New isolated unit `app/streaming/panel_localizer.py`:

```
localize(kind: str, data: dict, language: str, translator) -> dict
```

- `language == "en"` → **identity no-op** (default path unchanged, zero cost).
- **Bounded strings → deterministic Vietnamese lookup tables** (no LLM):
  - weather `description` — a `vi` sibling of `WMO_CODES`
  - AQI `category` / `advice` — `vi` siblings of the fixed dicts in `panels.py` (the
    `emoji` field is language-independent and is **not** localized)
  - place `category` — `vi` labels keyed off `CATEGORY_META`
  - hotel `amenities` — `vi` map over the bounded seeded amenity set
  This mirrors the `resolve_category()` "deterministic backend over LLM-reliance"
  precedent (`docs/solutions/agent/reflection-humanmessage-language-flip-decisions.md`).
- **Free-form prose (place `description` only) → injected fast-LLM pass**:
  the places panel is the only payload carrying free-form text. Translate when
  `language != "en"`, prompt instructs "translate descriptive text, keep proper nouns
  intact". Cache by `(text, language)` (module-level dict) so the finite set of seeded
  descriptions is translated at most once per language per process. (Hotel descriptions
  are **not** in the panel payload today; surfacing them would require adding a field to
  the hotel projection + a FE renderer change — out of scope per §3.)
- **Failure handling:** translator error/timeout → fall back to the English string
  (never block the panel); `logger.error("[PANEL_LOCALIZER] ...: %s", e)`.

Wiring in `mapper.py`:
- Track `current_language` (default `"en"`), seeded from the persisted state at stream
  start (covers resume turns), updated whenever an `updates` delta carries `language`.
  Today `graph.aget_state(cfg)` runs only *after* the drain (`mapper.py:181`); seeding on
  resume turns needs an added pre-loop `aget_state` await to read the sticky `language`.
- At the `panel` emission (`mapper.py:164`), call `localize(...)` before yielding.
- Localization replaces the user-visible English strings (e.g. AQI/place `category`) with
  Vietnamese. This is display-only: the FE keys UI logic off structured fields (AQI `band`,
  panel `kind`), not the localized `category` text — confirm no renderer branches on the
  English `category`/`advice` string before shipping.
- The `translator` is an **injected handle** resolved at lifespan (same pattern as
  `graph.extract_memory_llm`) and threaded into `stream_agent_events`. Tests inject a
  fake translator or rely on the `en` no-op, so no network access.

## 8. Stream contract (public-contract change)

- Add `language: str` to the `panel` event payload — `app/streaming/events.py` +
  `app/streaming/panels.py`, mirrored in `apps/web/src/lib/stream/panel.ts`. Self-contained
  per panel → no event-ordering dependency (`start` fires before language is known, so the
  tag is not placed there).
- Add `language` to the `done` event for a conversation-level record.
- `ChatRequest` is unchanged.

## 9. Frontend

- Extend the existing `next-intl` pattern to `apps/web/src/components/chat/panel/*`:
  move `PANEL_LABELS` and the hardcoded literals in each renderer into a new `Panel`
  namespace in `messages/en.json` + `messages/vi.json`, consumed via `useTranslations`.
- Panel static labels follow the **streamed** language, not the cookie: a scoped
  `NextIntlClientProvider` (or a `usePanelLocale(language)` hook) around the panel subtree
  using the `language` from `useAgentStream`'s `panel`/`done` events. `useAgentStream.ts`
  stores the streamed language alongside `panels[]`.
- Dynamic content is already localized server-side and rendered as-is.

## 10. Testing

- **Backend**
  - `panel_localizer` unit: deterministic lookup tables per kind (weather/AQI/category/
    amenities) return Vietnamese; unknown language falls back to English.
  - `panel_localizer` prose: injected fake translator localizes the **places** panel
    `description`; translator error falls back to English.
  - `en` regression: panels byte-identical to current output.
  - `mapper` propagation: a supervisor `updates` delta with `language="vi"` results in a
    `panel` event tagged `vi` and localized data.
  - supervisor: `intent.language` is persisted into state.
  - conversation-level detection (§6.1): a Vietnamese-dominant history whose latest
    message is a lone "ok"/"fine" still yields `language="vi"` (dominant + sticky), not
    "en" — a `FakeLLM`/scripted-supervisor test pinning the sticky behavior.
- **Frontend**
  - panel labels render Vietnamese when the stream reports `vi`; English on `en`.
  - `tsc --noEmit`, `eslint`, `next build` pass.

## 11. Risks

- **Supervisor-skipped turns** (HITL resume) don't re-detect language → mitigated by the
  sticky checkpoint value + seeding `current_language` from persisted state at stream start.
- **Detection reliability** — `intent.language` is LLM-derived; a very short/mixed message
  could mis-detect. Mitigated by §6.1 (conversation-level dominant detection + stickiness),
  so a lone "ok"/"fine" turn does not flip the panel. It also shares lineage with the reply
  language, so panel and reply stay *consistent* even if both are occasionally "wrong". (A
  deterministic library detector was considered and rejected — see §12.)
- **Translation latency** — the prose LLM pass adds latency between tool result and panel
  event, only when `language != "en"` and only for panels with descriptions; cache
  amortizes repeats. Lookup-table strings are synchronous.
- **FakeLLM leakage** — a direct `get_fast_llm()` call in the streaming layer would bypass
  the test double and hit the network; mitigated by the injected-handle pattern.
- **Public-contract gate** — new `panel.language` trips `risk-corroboration.sh`; commit
  with `RISK_WARN_CATEGORIES="public-contract"` (see memory `public-contract-hard-gate`).

## 12. Alternatives considered

- **Frontend-only static-label fix** — leaves dynamic content English. Rejected by user
  (wants full consistency).
- **Follow the UI-locale cookie** instead of detected typed language. Rejected: the reply
  follows the typed language; the cookie would desync the panel from the conversation.
- **Add `ChatRequest.locale`** and have the FE send it. Unnecessary once detection is
  backend-side from the message; larger public-contract surface.
- **Deterministic library detector** (`lingua`/`langdetect`) at the router. Rejected in
  favor of reusing `SupervisorIntent.language`: no new dependency, and it shares the LLM's
  reply-language judgment. (Kept as a documented fallback if supervisor detection proves
  unreliable.)
- **Latest-message-only detection.** Rejected (§6.1): a lone language-neutral interjection
  ("ok", "fine", "good") would flip the panel to English while the context-aware reply
  stays Vietnamese — re-creating the divergence this fix targets. Detection is
  conversation-level and sticky instead.
- **Locale-aware seed data** (Vietnamese description columns) for prose instead of the LLM
  pass. Rejected by user in favor of the LLM pass at emission (handles arbitrary prose).
- **Localize inside each tool** (via `InjectedState`) instead of the mapper seam. Rejected:
  touches every tool and hits the `InjectedState`/`args_schema` injection pitfall (memory
  `explicit-args-schema-breaks-langgraph-injection`); the mapper seam centralizes it.

## 13. Affected files (indicative)

- Backend: `app/agents/state.py`, `app/agents/supervisor.py`, the supervisor prompt in
  `app/prompts/` (conversation-level detection guidance, §6.1) and possibly
  `system_with_summary` (`app/agents/state.py`) to feed the established language,
  `app/streaming/panel_localizer.py` (new), `app/streaming/mapper.py`,
  `app/streaming/events.py`, `app/streaming/panels.py`, `app/core/lifespan.py` (inject
  translator handle), plus `app/data/` lookup-table siblings; tests under `tests/`.
  (Note: editing a prompt requires a graph rebuild to take effect — memory
  `prompt-changes-need-graph-rebuild-not-hot-reloaded`.)
- Frontend: `apps/web/src/components/chat/panel/*`,
  `apps/web/src/components/chat/useAgentStream.ts`,
  `apps/web/src/lib/stream/panel.ts`, `apps/web/messages/{en,vi}.json`.
