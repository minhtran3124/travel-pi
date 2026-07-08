# Research Brief — MIN-57 side-panel language consistency

_Depth: **Deep** (high-blast `core/lifespan.py` + `prompts/active.yaml`; shared contract `TravelAgentState`; public contract = SSE `panel`/`done` event shape). Companion to `design.md`._

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Reuse existing** — no new dependency, no new subsystem. Extend the seams already present (`SupervisorIntent.language`, the `mapper.py` panel-emission point, the installed `next-intl`). |
| **Why this is the lightest credible path** | Every capability needed already exists in-repo; the work is persisting one discarded field, adding one localization pass at an existing seam, tagging two events, and extending an installed i18n lib to a subtree it missed. |
| **Confidence** | 88% |
| **Next step** | Proceed to `/writing-plans`. One product decision is already settled by the user (prose = LLM pass; detection = conversation-level sticky); remaining items are implementation-level. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | pnpm + Turborepo monorepo (FastAPI backend `apps/api/` + Next.js frontend `apps/web/`) |
| Primary language + runtime | Python 3.10+ (`apps/api`), TypeScript / Node v24 (`apps/web`) |
| Frameworks / platforms | FastAPI, SQLAlchemy, Alembic; **LangGraph 1.x + LangChain 1.x** agent layer; Next.js App Router |
| Relevant packages | `next-intl ^4.13.0` (installed, cookie-driven, no i18n routing); `init_chat_model` LLM client; LangGraph checkpointer |
| Detectable versions | `next-intl@^4.13.0` (`apps/web/package.json`); AI deps capped: `fastapi<0.137`, `starlette<1.3`, `pydantic<3` (`requirements*.txt`) |
| Important constraints | Services raise domain exceptions (not `HTTPException`); async only for real I/O; **prompt edits need a graph rebuild** (uvicorn `--reload` watches only `.py`); AI-dep caps are load-bearing; deterministic seed algorithm must not change |

---

## Feature Understanding and Assumptions

- **Requested feature:** Make the chat **side panel** render in the user's language (Vietnamese) instead of English — full-stack, covering static labels + dynamic content, keyed off the **dominant conversation language** (not the UI cookie, not the single latest message).
- **What success appears to mean:** A Vietnamese conversation shows Vietnamese panel labels + weather/AQI/category/amenities + place descriptions; a lone "ok"/"fine" turn does not flip the panel; the `en` path is byte-identical to today.
- **Assumptions from the request (settled with the user):** prose (place `description`) via an injected fast-LLM pass; language source = reuse `SupervisorIntent.language` (LLM), conversation-level + sticky.
- **Assumptions still needing confirmation:** (1) FE keys no UI logic off the English `category`/`advice` strings (localizing replaces them) — must verify before shipping; (2) hotel descriptions are out of scope because the hotel panel projection carries none (confirmed in code).

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `SupervisorIntent.language` (`app/agents/supervisor.py:37`) is detected every turn but **discarded** — line 84 persists only `current_flow`. |
| `Local` | Supervisor already sees the **whole conversation**: `router.invoke([system_with_summary(state, system), *state["messages"]])` (`supervisor.py:54`) → conversation-level detection needs no new plumbing, just prompt guidance + feeding prior `state["language"]`. |
| `Local` | Panels are built in English at **tool-execution** time and emitted at `app/streaming/mapper.py:164` from `ToolMessage.artifact` — the single seam to localize + tag. Supervisor runs before any tool, so language is known first. |
| `Local` | Dynamic text is static English, **not** provider/LLM-generated: weather `WMO_CODES` (`weather_service.py:35`), AQI `_AQI_BAND/_AQI_EMOJI/_AQI_ADVICE` (`panels.py:206-233`), place `category` + `description` (`data/places.py`), hotel `amenities` (`data/hotels.py`). Open-Meteo/ORS return numbers only. |
| `Local` | **Only `PlacesPanelPlace` carries `description`** (`panels.py:537`); `HotelsPanelHotel` exposes `amenities` but **no** description (`panels.py:400-415`) → prose pass is places-only; hotels covered by bounded `amenities` lookup. |
| `Local` | `next-intl@4.13` installed cookie-driven (`src/i18n/{config,request,locale}.ts`, `messages/{en,vi}.json`, 356 keys); chat **shell** migrated by `i18n-vietnamese` but `components/chat/panel/*` was **not** (`registry.ts` `PANEL_LABELS` + `HotelsPanel.tsx` literals still hardcoded English). |
| `Local` | LLM one-off handle: `get_fast_llm()` (`app/clients/llm.py:111`) via `init_chat_model`; tests inject `FakeLLM` (`llm.py:155`). A direct `get_fast_llm()` in the streaming layer would **bypass** the test double and hit the network → must use an **injected handle** (pattern: `graph.extract_memory_llm`, `agent.py:269`). |
| `Local` | `ChatRequest` (`app/schemas/agent.py:16`) has no locale field and needs none — detection is backend-side. |
| `Docs` | next-intl: a **nested `NextIntlClientProvider`** accepts explicit `locale` + `messages` props to override the ambient/cookie locale for a subtree; client components may add another provider instance for parts of the app (Context7 `/amannn/next-intl`, configuration + server-client-components docs). |
| `Local` | Prior art / precedent: `docs/solutions/agent/reflection-humanmessage-language-flip*` — (a) internal messages must be `SystemMessage` not `HumanMessage` where a rule keys off "latest message"; (b) **prefer deterministic backend mechanisms over LLM-reliance** (`resolve_category`) — supports lookup tables for bounded strings. |
| `Local` | SSE consumption: `useAgentStream.ts` + `lib/stream/parseSSE.ts`; `panel` events carry JSON `data`, so adding a `language` field is a trivial parse extension (`docs/solutions/streaming/agent-sse-on-nextjs.md`). |
| `Local` | Public-contract commit gate: our lane is **high-risk**, so `risk-corroboration.sh` won't block; if it fires, `RISK_WARN_CATEGORIES="public-contract"` is the sanctioned override (`docs/solutions/harness/public-contract-gate-warn-only.md`). |

---

## Local Findings

- **Relevant files / seams:** `app/agents/supervisor.py`, `app/agents/state.py` (`TravelAgentState`, `system_with_summary`), `app/streaming/{mapper.py,panels.py,events.py}`, `app/clients/llm.py`, `app/core/lifespan.py`, `app/prompts/active.yaml` (supervisor prompt), `app/data/{places.py,hotels.py}`, `app/services/weather_service.py`; FE `components/chat/panel/*`, `components/chat/useAgentStream.ts`, `lib/stream/panel.ts`, `messages/{en,vi}.json`.
- **Existing abstractions / extension points:** structured-output `SupervisorIntent` (already emits `language`); the `mapper.py` panel-emission branch; the injected-LLM-handle-on-graph pattern (`extract_memory_llm`); installed `next-intl` with nested-provider support; `describe_code()` / lookup dicts ready to gain `vi` siblings.
- **Conventions worth preserving:** deterministic-over-LLM for bounded values; `SystemMessage` for internal notes; module-scoped logger with `[COMPONENT]` prefix; async only for real I/O; injected LLM handles so `FakeLLM` tests stay offline.
- **What can likely be reused:** ~all of it — detection (supervisor), emission seam (mapper), i18n lib (next-intl), LLM handle pattern (extract_memory_llm), the `vi.json` catalog scaffolding.
- **What appears missing locally:** (1) persistence of `intent.language` into state; (2) a `panel_localizer` unit (new) with `vi` lookup tables + injected prose translator; (3) `language` on the `panel`/`done` events + FE type mirror; (4) next-intl wiring for `panel/*` keyed off the streamed language; (5) conversation-level/sticky detection guidance in the supervisor prompt.

---

## Upstream Findings

- **Repositories inspected:** none needed — the pattern is fully in-repo. LangGraph's structured-output + state-channel model and next-intl's nested provider are the relevant upstream capabilities, both already available via installed versions.
- **Pattern already present:** LangGraph persisting a structured-output field into a state channel is idiomatic (`Command(update=...)`); next-intl nested `NextIntlClientProvider` for a subtree locale is a documented first-class feature.
- **Match closeness:** exact — no adaptation of external code required.

---

## Docs Findings

- **Official sources checked:** next-intl docs via Context7 (`/amannn/next-intl`, configuration + server-client-components), version-matched to the installed 4.x line.
- **Built-in capability that already supports the feature:** `NextIntlClientProvider` inherits `locale`/`messages`/`formats` from a parent but a **nested instance can override them** for a subtree, and explicit `messages` can be passed for a chosen locale. This is exactly the "panel follows the streamed language, not the cookie" requirement.
- **Recommended approach:** wrap the panel subtree in a nested provider with `locale={streamedLanguage}` and `messages={panelMessages[streamedLanguage]}`. Because the language is only known at runtime (from the stream) inside a client component, statically import both locales' small `Panel` slice on the client and select by streamed language (2 locales, tiny namespace → negligible bundle cost).
- **Caveats:** opt-out of prop inheritance where needed (`messages={null}`); keep the panel provider scoped so the rest of the app still follows the cookie locale.

---

## Recommendation

- **Primary recommendation:** **Reuse existing** across the board (detection, emission seam, i18n lib, LLM-handle pattern).
- **Why this is the lightest credible path:** the only genuinely new artifact is `panel_localizer.py`; everything else is a persist-the-discarded-field / tag-two-events / extend-an-installed-lib change. No new dependency, no schema/migration, no new provider, no `ChatRequest` change.
- **Why the next-best alternative lost:** a deterministic language-detection library (`lingua`/`langdetect`) adds a dependency and a second language notion that could disagree with the LLM's actual reply language — reusing `SupervisorIntent.language` shares the reply's lineage and ships zero deps. Localized seed columns for prose were rejected by the user in favor of the LLM pass.
- **What would change this recommendation:** if `SupervisorIntent.language` proves unreliable in practice (very short/code-switched turns even with the conversation-level + sticky prompt), fall back to the documented library detector (§12 of `design.md`).

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - **FakeLLM leakage** — the prose translator MUST be an injected handle resolved at lifespan; a direct `get_fast_llm()` in `mapper.py` would hit the network in tests. (High-blast `lifespan.py` edit → Deep.)
  - **Category-string keying** — localizing `category`/`advice` replaces English display strings; verify no FE renderer branches on those strings (AQI `band`/panel `kind` are the intended keying channels).
  - **Resume-turn language** — turns skipping the supervisor need `current_language` seeded from persisted state; today `graph.aget_state(cfg)` runs only post-drain (`mapper.py:181`) → add a pre-loop read.
  - **Prompt-change staleness** — the supervisor-prompt edit needs a graph rebuild to take effect (uvicorn `--reload` watches only `.py`); tests build a fresh graph so they're fine, but manual verification must force a rebuild.
  - **Translation latency** — prose LLM pass adds latency only when `language != en` and only for places panels; cache by `(text, language)`.
- **Evidence gaps:** exact `panel`/`done` event constructors in `events.py` not line-verified here (confirmed to exist; shape read at plan time); FE renderer audit for English-string keying deferred to implementation.
- **Version uncertainties:** none material — next-intl 4.x nested-provider API confirmed against installed line.
- **Follow-up questions for the user:** none blocking (both product forks already decided). Optional: confirm you're fine with the `en` path staying byte-identical (i.e. zero behavior change for English users) — assumed yes.

---

## Source Pack

- **Local files read:** `app/agents/supervisor.py`, `app/streaming/mapper.py`, `.claude/skills/xia2/PROJECT.md`, `docs/solutions/INDEX.md`, `docs/solutions/critical-patterns.md`, `docs/solutions/agent/reflection-humanmessage-language-flip{,-decisions}.md`, `docs/solutions/harness/public-contract-gate-warn-only.md`, `docs/solutions/streaming/agent-sse-on-nextjs.md`, `specs/i18n-vietnamese/PLAN.md`, `specs/agent-summary-panel-mismatch/SUMMARY.md`, plus the two Explore-agent sweeps of `apps/web/src/components/chat/panel/*`, `app/streaming/panels.py`, `app/data/*`, `app/schemas/agent.py`, `app/clients/llm.py`.
- **Upstream repositories/pages checked:** none required.
- **Official docs checked:** Context7 `/amannn/next-intl` (configuration; server-client-components).

---

## Evidence Boundary

> **Confirmed from artifacts:** `SupervisorIntent.language` exists + is discarded; supervisor sees full history; panels emitted at `mapper.py:164`; dynamic text is static English (seed + lookup dicts); only places carry `description`; `next-intl@4.13` installed, panel subtree not migrated; `get_fast_llm`/`FakeLLM` + injected-handle pattern; next-intl nested-provider locale override is supported.
> **Inferred from patterns:** conversation-level + sticky detection will hold via prompt guidance + prior-language feed (reasoned from the supervisor already seeing full history); localizing `category`/`advice` is display-safe (pending the FE keying audit).
> **Not checked:** exact `events.py` panel/done constructor signatures (line-level); a full FE audit for English-string keying; live behavior of supervisor language detection on adversarial code-switched input.
