---
slug: min-57-side-panel-language
status: active
owner: Minh Tran
created: 2026-07-08
linear: MIN-57
lane: high-risk
---

# Side-Panel Language Consistency (Vietnamese) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Make the chat side panel render in the user's dominant conversation language (Vietnamese) — static labels *and* dynamic content — instead of always English.

**Architecture:** The supervisor already detects `SupervisorIntent.language` every turn but discards it. Persist it into `TravelAgentState.language` (conversation-level + sticky via prompt guidance), localize panel content at the single `mapper.py` emission seam (deterministic `vi` lookup tables for bounded strings + an injected fast-LLM pass for place descriptions), tag the SSE `panel`/`done` events with the language, and extend the installed `next-intl` to the `panel/*` subtree via a nested provider keyed off the streamed language. No new dependency, no schema/migration, no `ChatRequest` change.

**Tech Stack:** Python 3.10+ / FastAPI / LangGraph 1.x / LangChain (`init_chat_model`, `FakeLLM`); Next.js App Router / `next-intl ^4.13` / TypeScript / Node v24.

**Reference artifacts:** `specs/min-57-side-panel-language/design.md`, `specs/min-57-side-panel-language/research-brief.md`.

---

## 1. Motivation

Chat replies mirror the traveller's language (Vietnamese) but the side panel stays English — an inconsistent experience (MIN-57). Two string sources cause it: hardcoded FE labels in `panel/*` (never migrated to the existing `next-intl`), and English dynamic content from the SSE `panel` stream (seeded data + local lookup tables, never localized).

## 2. Non-goals

- No UI-cookie coupling (panel follows the **detected** language, not the switcher).
- No `ChatRequest` field; detection is backend-side.
- No third language; `en`+`vi` only.
- No hotel-description translation (the hotel panel projection carries no description; hotels are covered by the bounded `amenities` lookup).
- No change to panel *kinds*, the REST API, or the deterministic seed algorithm.
- No new language-detection dependency (reuse `SupervisorIntent.language`).

## 3. Success Criteria

1. A fully-Vietnamese conversation yields Vietnamese panel labels + weather/AQI/category/amenities + place descriptions.
2. A lone language-neutral turn ("ok"/"fine") does **not** flip the panel (conversation-level + sticky).
3. `language == "en"` path is byte-identical to today (regression-proven).
4. Backend tests run offline (injected translator / `en` no-op — no network).
5. `apps/api` suite green; `apps/web` `tsc --noEmit` + `lint` + `build` pass.

## 4. Risks

- **FakeLLM leakage** — the prose translator must be an injected handle (`graph.translate_llm`); never call `get_fast_llm()` directly in `mapper.py`.
- **Category-string keying** — localizing `category`/`advice` replaces English display strings; verify no FE renderer branches on them (band/kind are the keying channels).
- **Resume turns** — seed `current_language` from persisted state before the astream loop.
- **Prompt staleness** — the supervisor-prompt edit needs a graph rebuild to take effect at runtime (tests build a fresh graph, so they are unaffected).
- **Public-contract gate** — high-risk lane won't be blocked; if `risk-corroboration.sh` fires on the SSE-contract change, commit with `RISK_WARN_CATEGORIES="public-contract"`.

## 5. Wave Map

| Wave | Tasks | Parallelism | Disjoint files |
|------|-------|-------------|----------------|
| 1 | 1.1 state field · 1.2 event tags · 1.3 panel_localizer (new) | 3 parallel | `state.py` / `events.py` / `panel_localizer.py` |
| 2 | 2.1 supervisor+prompt · 2.2 graph handle | 2 parallel | `supervisor.py`+`active.yaml` / `graph.py` |
| 3 | 3.1 mapper integration | single | `mapper.py` |
| 4 | 4.1 message catalogs · 4.2 stream types+store | 2 parallel | `messages/*.json` / `panel.ts`+`useAgentStream.ts` |
| 5 | 5.1 panel UI + nested provider | single | `components/chat/panel/*` |
| 6 | 6.1 acceptance | single | test files only |

BE test command: `cd apps/api && ../../.venv/bin/python -m pytest <path> -x`
FE (Node v24): `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"; cd apps/web && pnpm --filter web exec tsc --noEmit && pnpm --filter web lint`

---

## 6. Tasks

### Task 1.1 — Add `language` to graph state

**Files:**
- Modify: `apps/api/app/agents/state.py` (add field to `TravelAgentState`)
- Test: `apps/api/tests/agents/test_state_language.py` (create)

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/agents/state.py, apps/api/tests/agents/test_state_language.py</files>
  <action>Add `language: str  # dominant conversation language code (e.g. "en"/"vi"); default "en" set by supervisor` to TravelAgentState, placed after `current_flow`. It is a plain optional state channel (TravelAgentState is a TypedDict via MessagesState — no default needed; readers use state.get("language", "en")). Do NOT add a reducer.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state_language.py -x</verify>
  <done>State accepts and round-trips a `language` key; test passes.</done>
</task>
```

- [ ] **Step 1: Write the failing test** — `apps/api/tests/agents/test_state_language.py`

```python
from app.agents.state import TravelAgentState


def test_state_carries_language():
    state: TravelAgentState = {"messages": [], "language": "vi"}
    assert state.get("language") == "vi"


def test_state_language_absent_defaults_via_get():
    state: TravelAgentState = {"messages": []}
    assert state.get("language", "en") == "en"
```

- [ ] **Step 2: Run — expect FAIL** (or type error). Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state_language.py -x`
- [ ] **Step 3: Implement** — in `apps/api/app/agents/state.py`, inside `TravelAgentState`, add after `current_flow: str  # ...`:

```python
    language: str  # dominant conversation language code (e.g. "en"/"vi"); set by supervisor
```

- [ ] **Step 4: Run — expect PASS.**

---

### Task 1.2 — Tag `panel` and `done` SSE events with `language`

**Files:**
- Modify: `apps/api/app/streaming/events.py:70` (`panel`), `:78` (`done`), and the taxonomy docstring
- Test: `apps/api/tests/streaming/test_events_language.py` (create)

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/streaming/events.py, apps/api/tests/streaming/test_events_language.py, apps/api/tests/api/agent/test_stream_events.py</files>
  <action>Add a `language: str = "en"` keyword param to `events.panel(...)` and `events.done(...)`, folding it into the JSON payload. Default "en" keeps existing call sites and the en path byte-identical when language is unset. Update the taxonomy docstring lines for `panel` and `done` to include `language`. NOTE (shared-contract): `tests/api/agent/test_stream_events.py` pins the exact panel/done payload shape with `==`; update its three shape assertions (`test_done_factory_shape`, `test_panel_factory_shape`, `test_mapper_emits_panel_before_tool_result`) to include `"language": "en"`. This file was missed at plan time (wave-shared-file-partition) and fixed during Wave 3.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_events_language.py -x</verify>
  <done>panel/done payloads include `language`; default is "en".</done>
</task>
```

- [ ] **Step 1: Failing test** — `apps/api/tests/streaming/test_events_language.py`

```python
import json

from app.streaming import events


def test_panel_defaults_language_en():
    ev = events.panel(tool_call_id="t1", kind="weather", data={})
    assert json.loads(ev.data)["language"] == "en"


def test_panel_carries_language():
    ev = events.panel(tool_call_id="t1", kind="weather", data={}, language="vi")
    assert json.loads(ev.data)["language"] == "vi"


def test_done_carries_language():
    ev = events.done(conversation_id="c1", current_flow="concierge", language="vi")
    assert json.loads(ev.data)["language"] == "vi"
```

- [ ] **Step 2: Run — expect FAIL** (unexpected `language` kwarg).
- [ ] **Step 3: Implement** — edit `events.py`:

```python
def panel(*, tool_call_id: str, kind: str, data: Any, language: str = "en") -> TypedSSEEvent:
    return _event(
        "panel",
        {"tool_call_id": tool_call_id, "kind": kind, "data": data, "language": language},
    )


def done(*, conversation_id: str, current_flow: str | None, language: str = "en") -> TypedSSEEvent:
    return _event(
        "done",
        {"conversation_id": conversation_id, "current_flow": current_flow, "language": language},
    )
```

Update the docstring lines to `... {tool_call_id, kind, data, language}` and `... {conversation_id, current_flow, language}`.

- [ ] **Step 4: Run — expect PASS.** Also run the existing streaming suite to confirm the default keeps things green: `cd apps/api && ../../.venv/bin/python -m pytest tests/streaming -x`.

---

### Task 1.3 — New `panel_localizer` unit (lookup tables + injected prose pass)

**Files:**
- Create: `apps/api/app/streaming/panel_localizer.py`
- Test: `apps/api/tests/streaming/test_panel_localizer.py` (create)

```xml
<task id="1.3" wave="1">
  <files>apps/api/app/streaming/panel_localizer.py, apps/api/tests/streaming/test_panel_localizer.py</files>
  <action>Create `localize_panel(kind, data, language, translator=None) -> dict`. For language=="en" or unknown, return data unchanged (identity — do not copy-mutate the caller's dict on the en path; return it as-is). For "vi": deep-copy data, then (a) replace bounded strings via module-level VI lookup tables keyed on the canonical English value, using the REAL panels.py field names: weather `current.description` + each `daily[].description`; air_quality top-level `category` + `advice` + each `forecast[].category` (per-day carries only category/band — NO desc/advice); places top-level `category` + each `places[].category`; hotels each `hotels[].amenities` item; (b) for kind=="places" translate each `places[].description` via the injected `translator` callable (str->str) when provided, else leave English. Guard-clause every lookup: unknown English value falls through unchanged. Wrap the translator call in try/except → on error log `logger.error("[PANEL_LOCALIZER] translate failed: %s", e)` and keep the English string. The VI tables MUST have one entry per canonical English value in the source dicts: `set(WMO_CODES.values())` (weather_service.py) → WEATHER_VI; `set(_AQI_BAND)` KEYS (panels.py — the keys ARE the English categories) → AQI_CATEGORY_VI; `set(_AQI_ADVICE.values())` (panels.py) → AQI_ADVICE_VI; place category source keys → CATEGORY_VI; seeded amenity set (data/hotels.py) → AMENITY_VI. A parity test enforces this.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_panel_localizer.py -x</verify>
  <done>en path returns identical object; vi path localizes bounded strings via lookup + place description via injected translator; translator error falls back to English; parity test green.</done>
</task>
```

- [ ] **Step 1: Failing tests** — `apps/api/tests/streaming/test_panel_localizer.py`

```python
import pytest

from app.streaming.panel_localizer import localize_panel
from app.streaming import panel_localizer as pl


def test_en_is_identity():
    data = {"current": {"description": "Clear sky"}}
    out = localize_panel("weather", data, "en")
    assert out is data  # no copy, no change on the default path


def test_unknown_language_is_identity():
    data = {"current": {"description": "Clear sky"}}
    assert localize_panel("weather", data, "fr") is data


def test_vi_localizes_weather_description():
    data = {"current": {"description": "Clear sky"}, "daily": []}
    out = localize_panel("weather", data, "vi")
    assert out["current"]["description"] == pl.WEATHER_VI["Clear sky"]
    assert out is not data  # copied, original untouched
    assert data["current"]["description"] == "Clear sky"


def test_vi_unknown_bounded_value_passes_through():
    out = localize_panel("weather", {"current": {"description": "??"}, "daily": []}, "vi")
    assert out["current"]["description"] == "??"


def test_vi_places_description_uses_translator():
    calls = []

    def translator(text: str) -> str:
        calls.append(text)
        return "TRANSLATED:" + text

    data = {"places": [{"description": "A cozy cafe.", "category": "cafe"}]}
    out = localize_panel("places", data, "vi", translator=translator)
    assert out["places"][0]["description"] == "TRANSLATED:A cozy cafe."
    assert out["places"][0]["category"] == pl.CATEGORY_VI["cafe"]
    assert calls == ["A cozy cafe."]


def test_translator_error_falls_back_to_english():
    def boom(text: str) -> str:
        raise RuntimeError("no llm")

    data = {"places": [{"description": "A cozy cafe.", "category": "cafe"}]}
    out = localize_panel("places", data, "vi", translator=boom)
    assert out["places"][0]["description"] == "A cozy cafe."  # unchanged on error


def test_vi_air_quality_uses_forecast_key():
    data = {"category": "Good", "advice": "Air quality is fine.", "forecast": [{"category": "Good"}]}
    out = localize_panel("air_quality", data, "vi")
    assert out["category"] == pl.AQI_CATEGORY_VI["Good"]
    assert out["forecast"][0]["category"] == pl.AQI_CATEGORY_VI["Good"]


def test_vi_tables_cover_english_sources():
    """Parity: every canonical English value has a vi entry."""
    from app.services.weather_service import WMO_CODES
    from app.streaming.panels import _AQI_BAND, _AQI_ADVICE

    wmo_values = set(WMO_CODES.values())
    assert wmo_values <= set(pl.WEATHER_VI), wmo_values - set(pl.WEATHER_VI)
    # _AQI_BAND KEYS are the English category strings (values are band slugs).
    assert set(_AQI_BAND) <= set(pl.AQI_CATEGORY_VI), set(_AQI_BAND) - set(pl.AQI_CATEGORY_VI)
    assert set(_AQI_ADVICE.values()) <= set(pl.AQI_ADVICE_VI)


def test_vi_category_and_amenity_tables_cover_sources():
    """Parity for the two tables `_swap` would otherwise silently pass through."""
    # Adjust imports to the real category + seeded-amenity sources at implement time.
    from app.services.place_service import CATEGORY_META  # place category source
    from app.data.hotels import SEEDED_AMENITIES  # or derive the set from data/hotels.py

    assert set(CATEGORY_META) <= set(pl.CATEGORY_VI), set(CATEGORY_META) - set(pl.CATEGORY_VI)
    assert set(SEEDED_AMENITIES) <= set(pl.AMENITY_VI), set(SEEDED_AMENITIES) - set(pl.AMENITY_VI)
```

> If the exact symbol names (`WMO_CODES`, `_AQI_BAND`, `_AQI_ADVICE`) differ at implementation time, read `weather_service.py` and `panels.py` and adjust the parity test imports/keys to the real source dicts. The parity test is the guard that the tables are complete — keep it.

- [ ] **Step 2: Run — expect FAIL** (module missing).
- [ ] **Step 3: Implement** — `apps/api/app/streaming/panel_localizer.py`:

```python
"""Localize side-panel payloads to the traveller's language at emission time.

Bounded strings (weather/AQI/category/amenities) use deterministic VI lookup
tables keyed on the canonical English value — the `resolve_category` "deterministic
over LLM" precedent (docs/solutions/agent/reflection-humanmessage-language-flip-decisions.md).
Free-form place descriptions use an injected fast-LLM translator so tests stay
offline (never call get_fast_llm() here). English is a pure identity no-op.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# --- VI lookup tables (one entry per canonical English source value) ----------
# NOTE: fill EVERY key present in the English source dicts. The parity test
# (test_vi_tables_cover_english_sources) fails until these are complete.
WEATHER_VI: dict[str, str] = {
    "Clear sky": "Trời quang",
    "Mainly clear": "Phần lớn quang đãng",
    "Partly cloudy": "Có mây rải rác",
    "Overcast": "Nhiều mây",
    # ... one entry per WMO_CODES value (weather_service.py) ...
}

AQI_CATEGORY_VI: dict[str, str] = {
    "Good": "Tốt",
    "Moderate": "Trung bình",
    "Unhealthy for Sensitive Groups": "Không tốt cho nhóm nhạy cảm",
    "Unhealthy": "Có hại",
    "Very Unhealthy": "Rất có hại",
    "Hazardous": "Nguy hiểm",
    # ... one per _AQI_BAND value (panels.py) ...
}

AQI_ADVICE_VI: dict[str, str] = {
    # ... one per _AQI_ADVICE value (panels.py) ...
}

CATEGORY_VI: dict[str, str] = {
    "cafe": "quán cà phê",
    "restaurant": "nhà hàng",
    "bar": "quán bar",
    "museum": "bảo tàng",
    "park": "công viên",
    # ... one per CATEGORY_META key (place_service.py / place category source) ...
}

AMENITY_VI: dict[str, str] = {
    "Free WiFi": "WiFi miễn phí",
    "Pool": "Hồ bơi",
    "Gym": "Phòng gym",
    "Spa": "Spa",
    "Breakfast included": "Bao gồm bữa sáng",
    # ... one per seeded amenity (data/hotels.py) ...
}

Translator = Callable[[str], str]


def _swap(value: object, table: dict[str, str]) -> object:
    """Return the VI value for a canonical English string, else the value unchanged."""
    if isinstance(value, str):
        return table.get(value, value)
    return value


def localize_panel(
    kind: str, data: dict, language: str, translator: Translator | None = None
) -> dict:
    """Localize a panel ``data`` dict to ``language``. English/unknown → identity."""
    if language != "vi" or not isinstance(data, dict):
        return data
    out = copy.deepcopy(data)
    if kind == "weather":
        cur = out.get("current")
        if isinstance(cur, dict):
            cur["description"] = _swap(cur.get("description"), WEATHER_VI)
        for day in out.get("daily") or []:
            if isinstance(day, dict):
                day["description"] = _swap(day.get("description"), WEATHER_VI)
    elif kind == "air_quality":
        # panels.py: top-level category + advice; per-day list is `forecast`
        # (AirQualityPanelDay has category/band only — no advice/desc per day).
        if isinstance(out.get("category"), str):
            out["category"] = _swap(out["category"], AQI_CATEGORY_VI)
        if isinstance(out.get("advice"), str):
            out["advice"] = _swap(out["advice"], AQI_ADVICE_VI)
        for day in out.get("forecast") or []:
            if isinstance(day, dict):
                day["category"] = _swap(day.get("category"), AQI_CATEGORY_VI)
    elif kind == "places":
        # panels.py: top-level `category` (nullable) + list `places`
        if isinstance(out.get("category"), str):
            out["category"] = _swap(out["category"], CATEGORY_VI)
        for place in out.get("places") or []:
            if not isinstance(place, dict):
                continue
            place["category"] = _swap(place.get("category"), CATEGORY_VI)
            desc = place.get("description")
            if translator and isinstance(desc, str) and desc:
                try:
                    place["description"] = translator(desc)
                except Exception as e:  # noqa: BLE001 — keep English on failure
                    logger.error("[PANEL_LOCALIZER] translate failed: %s", e)
    elif kind == "hotels":
        for hotel in out.get("hotels") or []:  # panels.py: list `hotels`
            if isinstance(hotel, dict) and isinstance(hotel.get("amenities"), list):
                hotel["amenities"] = [_swap(a, AMENITY_VI) for a in hotel["amenities"]]
    return out
```

> **Implementer:** the key names above match `panels.py` at plan time (weather `current`/`daily`; air_quality top-level `category`/`advice` + `forecast[]`; places top-level `category` + `places[]`; hotels `hotels[]`). Re-confirm against `panels.py` before finalizing and keep the parity + per-kind tests as the guard against shape drift.

- [ ] **Step 4: Run — expect PASS** (fill tables until the parity test passes).

---

### Task 2.1 — Persist language + conversation-level sticky detection

**Files:**
- Modify: `apps/api/app/agents/supervisor.py:84` (persist), `:37` (field guidance), `:54` (feed prior language)
- Modify: `apps/api/app/prompts/active.yaml` (supervisor prompt — conversation-level rule)
- Test: `apps/api/tests/agents/test_supervisor_language.py` (create)

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/agents/supervisor.py, apps/api/app/prompts/active.yaml, apps/api/tests/agents/test_supervisor_language.py</files>
  <action>(1) In supervisor.py persist the detected language on the routing Command: `Command(update={"current_flow": target, "language": getattr(intent, "language", None) or state.get("language", "en")}, goto=next_node)` — falls back to the previous sticky value when the model omits one. (2) Update the `SupervisorIntent.language` Field description to instruct conversation-level dominant detection ignoring short interjections/loanwords. (3) Feed the established language into the routing prompt: extend the system message (or `system_with_summary`) with a line "Established conversation language: <state.language or 'unknown'>; keep it unless the traveller clearly switches." (4) In active.yaml, add to the supervisor prompt: detect the traveller's PRIMARY/DOMINANT language across the whole conversation; ignore lone interjections/loanwords ('ok','fine','good','sure'); only change on a clear sustained switch. Do NOT touch communication_style / sub-agent prompts.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_language.py tests/agents/test_supervisor.py -x</verify>
  <done>Supervisor persists language into state; empty-code fallback keeps the prior language; existing supervisor routing tests still pass. (Multi-turn "ok"-stays-vi stickiness proven in Task 6.1.)</done>
</task>
```

- [ ] **Step 1: Failing test** — `apps/api/tests/agents/test_supervisor_language.py`

```python
from langchain_core.messages import HumanMessage

from app.agents.supervisor import SupervisorIntent, make_supervisor


class _RouterLLM:
    """Fake structured-output LLM returning a scripted SupervisorIntent."""

    def __init__(self, intent):
        self._intent = intent

    def with_structured_output(self, *_a, **_k):
        return self

    def invoke(self, _messages):
        return self._intent


def test_supervisor_persists_language():
    llm = _RouterLLM(SupervisorIntent(target_agent="concierge", language="vi"))
    node = make_supervisor(llm)
    cmd = node({"messages": [HumanMessage("Thời tiết Đà Nẵng?")], "language": "en"}, None)
    assert cmd.update["language"] == "vi"


def test_supervisor_falls_back_to_state_when_code_empty():
    # An empty/unset code keeps the previously-established language (code fallback).
    llm = _RouterLLM(SupervisorIntent(target_agent="concierge", language=""))
    node = make_supervisor(llm)
    cmd = node({"messages": [HumanMessage("ok")], "language": "vi"}, None)
    assert cmd.update["language"] == "vi"
```

> **Implementer note (stickiness is prompt-driven, not code-locked):** the persist rule is
> `lang = getattr(intent, "language", None) or state.get("language", "en")` — the code fallback
> fires ONLY when the model returns a falsy/empty code, so it never permanently pins the language
> (a genuine switch still flows through `intent.language`). The real stickiness for the "ok"/"fine"
> case comes from Steps 3-4: seeding the supervisor with the established language + the
> conversation-level prompt rule, so the model itself returns "vi". Do NOT add code that forces
> `intent.language` to equal the previous state — that would lock the language. Multi-turn
> stickiness (vi history + "ok" → still vi) is proven in Task 6.1, not here, because it depends on
> model behavior the FakeLLM can only script per-turn.

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** persist + prompt feed in `supervisor.py` (see `<action>`), and the field description:

```python
    language: str = Field(
        default="en",
        description=(
            "The traveller's PRIMARY/DOMINANT language across the whole conversation "
            "(BCP-47-ish code, e.g. 'en'/'vi'). Ignore lone interjections and loanwords "
            "('ok','fine','good'); only report a different code on a clear, sustained switch."
        ),
    )
```

- [ ] **Step 4: Implement** the `active.yaml` supervisor-prompt addition (conversation-level rule).
- [ ] **Step 5: Run — expect PASS** (`test_supervisor_language.py` + existing `test_supervisor.py`).

---

### Task 2.2 — Attach the translator handle to the compiled graph

**Files:**
- Modify: `apps/api/app/agents/graph.py:155` (beside `compiled.extract_memory_llm`)
- Test: `apps/api/tests/agents/test_graph_translate_handle.py` (create)

```xml
<task id="2.2" wave="2">
  <files>apps/api/app/agents/graph.py, apps/api/tests/agents/test_graph_translate_handle.py</files>
  <action>After `compiled.extract_memory_llm = pick("extract_memory")` add `compiled.translate_llm = pick("extract_memory")` — reuse the same fast/injectable seam so a test's `fast_llm=`/`llm=` override reaches it and no network call happens. (If `pick` is keyed by agent-config name, reuse the existing "extract_memory" fast handle; a dedicated config is not required.) Expose it so `stream_agent_events(graph, ...)` can read `graph.translate_llm` with no signature change.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_graph_translate_handle.py -x</verify>
  <done>build_graph attaches a non-None `translate_llm`; a fake-injected build exposes the fake.</done>
</task>
```

- [ ] **Step 1: Failing test** — `apps/api/tests/agents/test_graph_translate_handle.py`

```python
from app.agents.graph import build_graph


def test_graph_exposes_translate_llm():
    graph = build_graph()  # match how other graph tests construct it (fakes/checkpointer)
    assert getattr(graph, "translate_llm", None) is not None
```

> Adjust `build_graph(...)` construction to the pattern used in existing `tests/agents/` (fake LLM + in-memory checkpointer). Reuse an existing conftest fixture if one builds the graph.

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** in `graph.py` after line 155:

```python
    compiled.translate_llm = pick("extract_memory")
```

- [ ] **Step 4: Run — expect PASS.**

---

### Task 3.1 — Wire localization + language tagging into the mapper

**Files:**
- Modify: `apps/api/app/streaming/mapper.py` (track language, seed pre-loop, localize at `panel`, tag `done`)
- Test: `apps/api/tests/streaming/test_mapper_language.py` (create)

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/streaming/mapper.py, apps/api/tests/streaming/test_mapper_language.py</files>
  <action>In stream_agent_events: (1) before the astream loop, seed `current_language = "en"` then try `pre = await graph.aget_state(cfg)` and set `current_language = (pre.values.get("language") if pre else None) or "en"` (covers resume turns; guard for None/errors). (2) Build a translator closure `translator = (lambda s: graph.translate_llm.invoke(s).content) if getattr(graph, "translate_llm", None) else None` — but only used when language=="vi". (3) In the `updates` branch, when a node delta carries `language`, update `current_language`. (4) At the panel emission, wrap: `panel_data = localize_panel(artifact["kind"], artifact.get("data"), current_language, translator=translator)` and pass `language=current_language` to `events.panel(...)`. (5) Pass `language=current_language` to the terminal `events.done(...)`. Keep the en path identical (localize_panel returns the same object). Import localize_panel from app.streaming.panel_localizer.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_mapper_language.py tests/streaming -x</verify>
  <done>A supervisor delta with language=vi produces a vi-tagged, vi-localized panel event and a vi-tagged done; en path unchanged; full streaming suite green.</done>
</task>
```

- [ ] **Step 1: Failing test** — `apps/api/tests/streaming/test_mapper_language.py`

```python
import json

import pytest

from app.streaming.mapper import stream_agent_events


class _FakeState:
    def __init__(self, values):
        self.values = values
        self.interrupts = []


class _FakeGraph:
    """Minimal graph stub: emits a supervisor language update then a weather panel."""

    translate_llm = None

    def __init__(self):
        self._events = [
            (("supervisor",), "updates", {"supervisor": {"language": "vi"}}),
            (
                ("concierge",),
                "updates",
                {"concierge": {"messages": [_ToolMsg("weather", {"current": {"description": "Clear sky"}, "daily": []})]}},
            ),
        ]

    async def astream(self, *_a, **_k):
        for e in self._events:
            yield e

    async def aget_state(self, _cfg):
        return _FakeState({"language": "vi", "current_flow": "concierge"})


# _ToolMsg: a stand-in ToolMessage with .artifact/.tool_call_id/.status — adjust to
# construct a real ToolMessage(artifact={"kind":..,"data":..}) as mapper expects.
```

> **Implementer:** the mapper reads real `ToolMessage` objects with an `artifact` dict — construct the test input with genuine `langchain_core.messages.ToolMessage(content="", tool_call_id="t1", artifact={"kind": "weather", "data": {...}})` rather than a stub if the mapper type-checks. Assert: collect events; the `panel` event's `data["current"]["description"]` equals the VI value and its `language == "vi"`; the `done` event's `language == "vi"`. Add a mirror test with an all-`en` stream asserting the panel `data` is byte-identical to input and `language == "en"`.

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** the five edits in `mapper.py` per `<action>`. Key snippet at the panel emission (replacing lines ~162-168):

```python
                            artifact = getattr(msg, "artifact", None)
                            if isinstance(artifact, dict) and "kind" in artifact:
                                panel_data = localize_panel(
                                    artifact["kind"],
                                    artifact.get("data"),
                                    current_language,
                                    translator=translator,
                                )
                                yield events.panel(
                                    tool_call_id=msg.tool_call_id,
                                    kind=artifact["kind"],
                                    data=panel_data,
                                    language=current_language,
                                )
```

And capture language from updates (inside the `for node_name, delta in ...` loop, before the message loop):

```python
                    node_lang = delta.get("language")
                    if isinstance(node_lang, str) and node_lang:
                        current_language = node_lang
```

And the terminal done: `yield events.done(conversation_id=conversation_id, current_flow=current_flow, language=current_language)`.

- [ ] **Step 4: Run — expect PASS** (targeted + full `tests/streaming`).

---

### Task 4.1 — Add the `Panel` message namespace (en + vi)

**Files:**
- Modify: `apps/web/messages/en.json`, `apps/web/messages/vi.json` (add a `Panel` namespace)
- Test: parity check (command below)

```xml
<task id="4.1" wave="4">
  <files>apps/web/messages/en.json, apps/web/messages/vi.json</files>
  <action>Add a `Panel` namespace to both catalogs containing every hardcoded label currently in components/chat/panel/* (tab labels from registry.ts PANEL_LABELS: Route/Places/Weather/Air Quality/Flights/Hotels; and HotelsPanel literals: "night(s)","left","full","available","Stars","Guest rating","reviews","Nightly rate","All-in total","Rooms left","Amenities","results","cheapest"; plus any literals in the other *Panel.tsx). Keys are stable identifiers; en values = current English; vi values = natural Vietnamese. Use ICU plural for count strings (nights, reviews, results). Do NOT remove or renumber existing keys.</action>
  <verify>export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"; cd apps/web && node -e "const a=require('./messages/en.json').Panel,b=require('./messages/vi.json').Panel;const f=(o,p='')=>Object.entries(o).flatMap(([k,v])=>typeof v==='object'?f(v,p+k+'.'):[p+k]);const miss=f(a).filter(k=>!new Set(f(b)).has(k));if(miss.length){console.error('missing vi Panel keys',miss);process.exit(1)}console.log('Panel parity',f(a).length)"</verify>
  <done>Both catalogs have a complete, parity-checked `Panel` namespace; no existing keys changed.</done>
</task>
```

- [ ] **Step 1:** Inventory every hardcoded literal in `apps/web/src/components/chat/panel/*` (grep for JSX text + string props).
- [ ] **Step 2:** Add the `Panel` namespace to `en.json` (English = current copy) and `vi.json` (Vietnamese).
- [ ] **Step 3:** Run the parity verify command — expect `Panel parity <n>`.

---

### Task 4.2 — Carry `language` on the panel stream + store it

**Files:**
- Modify: `apps/web/src/lib/stream/panel.ts` (add `language` to the panel event envelope type)
- Modify: `apps/web/src/components/chat/useAgentStream.ts` (`case "panel"` + `case "done"` store the conversation language)
- Test: `apps/web/src/components/chat/useAgentStream.test.ts` (extend or create)

```xml
<task id="4.2" wave="4">
  <files>apps/web/src/lib/stream/panel.ts, apps/web/src/lib/stream/parseSSE.ts, apps/web/src/components/chat/useAgentStream.ts, apps/web/src/components/chat/useAgentStream.stream.test.tsx</files>
  <action>(1) In panel.ts add `language?: string` to the panel *event* type (the {tool_call_id, kind, data} envelope, not the per-kind data interfaces). If the envelope type lives in useAgentStream/stream types, add it there. (2) In useAgentStream.ts, add a `panelLanguage` state (default "en"); set it from `evt.language` when present in EVERY `case "panel"` block — there are THREE (~lines 323/433/537 per the mapper/stream-consumer flows) — and in every `case "done"` block; expose `panelLanguage` alongside `panels`. Missing all handlers desyncs language across initial-load vs resume flows. Keep backward-compat: missing language → "en". Consider a single helper `setPanelLanguage(evt.language)` called from each case to avoid drift.</action>
  <verify>export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"; cd apps/web && pnpm --filter web exec tsc --noEmit && pnpm --filter web test -- useAgentStream</verify>
  <done>Hook exposes the streamed `panelLanguage`; types compile; test asserts vi panel event sets panelLanguage="vi".</done>
</task>
```

- [ ] **Step 1:** Read `useAgentStream.ts` to find where the parsed panel event is typed and where `panels[]` is updated (`upsertPanelByKind`).
- [ ] **Step 2:** Failing test: feed a `panel` event with `language:"vi"`; assert the hook's exposed `panelLanguage === "vi"`.
- [ ] **Step 3:** Add `language?: string` to the envelope type + `panelLanguage` state + assignment in `case "panel"`/`case "done"`.
- [ ] **Step 4:** Run tsc + the hook test — expect PASS.

---

### Task 5.1 — Localize the panel UI (nested provider + `useTranslations`)

**Files:**
- Create: `apps/web/src/components/chat/panel/PanelIntlProvider.tsx` (nested provider keyed off streamed language)
- Modify: `apps/web/src/components/chat/panel/registry.ts` (labels via keys), `SidePanel.tsx`, `HotelsPanel.tsx`, `PlacesPanel.tsx`, `WeatherPanel.tsx`, `AirQualityPanel.tsx`, `FlightsPanel.tsx`, `RoutePanel.tsx`
- Modify: `apps/web/src/components/chat/ChatPanel.tsx` (wrap the panel subtree in `PanelIntlProvider` with the streamed language)
- Test: `apps/web/src/components/chat/panel/SidePanel.test.tsx` (extend)

```xml
<task id="5.1" wave="5">
  <files>apps/web/src/components/chat/panel/PanelIntlProvider.tsx, apps/web/src/components/chat/panel/registry.ts, apps/web/src/components/chat/panel/SidePanel.tsx, apps/web/src/components/chat/panel/HotelsPanel.tsx, apps/web/src/components/chat/panel/PlacesPanel.tsx, apps/web/src/components/chat/panel/WeatherPanel.tsx, apps/web/src/components/chat/panel/AirQualityPanel.tsx, apps/web/src/components/chat/panel/FlightsPanel.tsx, apps/web/src/components/chat/panel/RoutePanel.tsx, apps/web/src/components/chat/ChatWidget.tsx, apps/web/src/components/chat/panel/*.test.tsx</files>
  <!-- Deviation: SidePanel is rendered by ChatWidget.tsx, not ChatPanel.tsx — the provider wrap landed in ChatWidget. Panel *.test.tsx files were wrapped in PanelIntlProvider (harness update). -->
  <action>(1) Create PanelIntlProvider: a client component taking `language: string` + children; statically import BOTH catalogs (`import en from "../../../../messages/en.json"; import vi from "../../../../messages/vi.json";`), pick the `Panel` slice for the streamed language (fallback en), and render `<NextIntlClientProvider locale={language} messages={{Panel: (language==="vi"?vi:en).Panel}}>{children}</NextIntlClientProvider>`. This overrides the ambient cookie locale for the panel subtree only (next-intl nested-provider pattern, per research-brief Docs findings). (2) Replace hardcoded literals in registry.ts PANEL_LABELS + each *Panel.tsx with `useTranslations("Panel")` keys matching Task 4.1. (3) In ChatPanel.tsx, wrap the SidePanel render with `<PanelIntlProvider language={panelLanguage}>` using the hook's streamed value. Do NOT change dynamic content rendering — server already localizes it. Adjust the relative import depth of the messages JSON to the real file location.</action>
  <verify>export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"; cd apps/web && pnpm --filter web exec tsc --noEmit && pnpm --filter web lint && pnpm --filter web test -- panel</verify>
  <done>Panel labels render from the `Panel` namespace in the streamed language; vi stream → Vietnamese labels; en unchanged; tsc/lint/tests pass.</done>
</task>
```

- [ ] **Step 1:** Failing test in `SidePanel.test.tsx`: render inside `PanelIntlProvider language="vi"`; assert a known label (e.g. tab "Weather") shows its Vietnamese value from `vi.json`.
- [ ] **Step 2:** Create `PanelIntlProvider.tsx`.
- [ ] **Step 3:** Migrate `registry.ts` + each `*Panel.tsx` literal to `useTranslations("Panel")` keys.
- [ ] **Step 4:** Wrap the panel subtree in `ChatPanel.tsx` with `PanelIntlProvider` using `panelLanguage`.
- [ ] **Step 5:** Run tsc + lint + panel tests — expect PASS.

---

### Task 6.1 — End-to-end acceptance

**Files:**
- Test: `apps/api/tests/streaming/test_panel_language_e2e.py` (create); FE build/smoke
- Modify: none (verification only)

```xml
<task id="6.1" wave="6">
  <files>apps/api/tests/streaming/test_panel_language_e2e.py</files>
  <action>Add a BE integration test driving the graph (FakeLLM supervisor returning language="vi" + a weather/places tool) through stream_agent_events with an injected fake translator; assert the emitted panel event is vi-tagged AND its bounded strings are Vietnamese AND the place description passed through the translator, and the done event is vi-tagged. Add an all-English mirror asserting byte-identical panel data + language="en". Add a STICKINESS scenario: prior state language="vi", supervisor FakeLLM scripted to return an empty/`en`-defaulted code for a short "ok" turn → assert persisted state language stays "vi" (proves the interjection case the 2.1 unit test could not). Then run the full BE suite and the FE build.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/streaming/test_panel_language_e2e.py -x && ../../.venv/bin/python -m pytest -q</verify>
  <done>E2E vi + en paths pass; full BE suite green.</done>
</task>
```

- [ ] **Step 1:** Write the vi + en e2e tests (reuse graph-build fixtures from `tests/agents`/`tests/streaming`; inject a fake `translate_llm` on the built graph).
- [ ] **Step 2:** Run the e2e file — expect PASS.
- [ ] **Step 3:** Run the full BE suite — expect PASS.
- [ ] **Step 4:** FE build: `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"; cd apps/web && pnpm --filter web build` — expect success.
- [ ] **Step 5:** Manual smoke (optional, needs Docker + Node24 playwright-core per repo memory): chat in Vietnamese, confirm panel labels + weather/AQI/category/amenities + a place description render Vietnamese; type "ok" and confirm the panel stays Vietnamese.

---

## 7. Verification Summary

| Wave | Gate |
|------|------|
| 1 | `pytest tests/agents/test_state_language.py tests/streaming/test_events_language.py tests/streaming/test_panel_localizer.py` |
| 2 | `pytest tests/agents/test_supervisor_language.py tests/agents/test_supervisor.py tests/agents/test_graph_translate_handle.py` |
| 3 | `pytest tests/streaming` |
| 4 | `pnpm --filter web exec tsc --noEmit` + Panel parity + `pnpm --filter web test -- useAgentStream` |
| 5 | `pnpm --filter web exec tsc --noEmit && pnpm --filter web lint && pnpm --filter web test -- panel` |
| 6 | full `pytest -q` + `pnpm --filter web build` |

Cross-engine parity once green: `cd apps/api && make test-docker`.

## 8. Rollback

- Revert each implementation commit: `git revert <sha>` (no DB migration → no `alembic downgrade` needed).
- The `en` default on every new param means a partial revert degrades gracefully to English panels.

## 9. Status Log

- 2026-07-08 — Plan drafted from `design.md` + `research-brief.md`. Lane high-risk. 6 waves / 10 tasks. Plan-review passed (2 iterations; localizer field-name fixes + parity-test coverage). Awaiting execution handoff.
