---
slug: streaming-panels-split
status: proposed
owner: Minh Tran
created: 2026-07-12
---

# Split `streaming/panels.py` into one module per panel kind, behind a registry

## 1. Motivation

`apps/api/app/streaming/panels.py` is 593 lines and holds all six panel kinds
(`route`, `weather`, `air_quality`, `flights`, `hotels`, `places`). The file size is the
symptom; the real cost is that **one panel kind is spread across three places**:

| Where | What lives there today |
| --- | --- |
| `app/streaming/panels.py` | the projection model + its `from_*` classmethod + presentation lookup tables (`_AQI_BAND`, `_COND_*`) |
| `app/streaming/panel_localizer.py` | the `vi` lookup tables (`WEATHER_VI`, `AQI_*_VI`, `CATEGORY_VI`, `AMENITY_VI`) + an `if kind == …` dispatch chain |
| `app/streaming/panels.py:29` | the `PanelKind` `Literal` — **dead**: nothing imports it (verified by grep across `app/` + `tests/`) |

So adding a seventh panel means editing three spots, and nothing enforces that the three
agree. `panel_result(summary, *, kind: str, data)` (`app/tools/_base.py:93`) takes a free-text
`kind` that **no caller validates** — a typo'd kind ships to the FE as a panel nobody renders.

After this change, adding a panel = **adding one file**.

## 2. Non-goals

- No change to the `panel` SSE event payload, to any `*Panel` field, or to the FE. This is
  behavior-preserving; `apps/web` is not touched.
- No change to the public import path: `from app.streaming.panels import HotelsPanel` keeps
  working (re-exported from the package `__init__`). `app/tools/*.py` import lines stay as-is.
- No new panel kinds, no new `vi` strings, no translator changes.
- No touching `mapper.py` — it imports `localize_panel` from `panel_localizer`, and that
  module keeps its name and its function signature.

## 3. Success Criteria

1. `app/streaming/panels/` is a package with one module per kind; no module exceeds ~150 lines.
2. Adding a panel kind requires creating exactly one file under `app/streaming/panels/` and
   nothing else — no edit to a `Literal`, no edit to `panel_localizer`'s dispatch.
3. `from app.streaming.panels import RoutePanel, WeatherPanel, AirQualityPanel, FlightsPanel, HotelsPanel, PlacesPanel` still resolves.
4. `panel_result()` rejects an unregistered `kind` instead of silently emitting it.
5. The existing suite passes unchanged except for imports of module-private names
   (`_AQI_BAND` / `_AQI_ADVICE`) that moved with their panel.

## 4. Tasks

### Task 1.1 — Package split: one module per kind + registry infra

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/streaming/panels.py, apps/api/app/streaming/panels/__init__.py, apps/api/app/streaming/panels/base.py, apps/api/app/streaming/panels/route.py, apps/api/app/streaming/panels/weather.py, apps/api/app/streaming/panels/air_quality.py, apps/api/app/streaming/panels/flights.py, apps/api/app/streaming/panels/hotels.py, apps/api/app/streaming/panels/places.py, apps/api/tests/streaming/test_panel_localizer.py</files>
  <action>Replace the module `app/streaming/panels.py` with a package `app/streaming/panels/`. This is ONE atomic task because a module and a package of the same name cannot coexist on the import path — `git rm` the old file in the same commit that adds the package.

`base.py` — the registry, and nothing panel-specific:
  - `PanelSpec` (frozen dataclass): `kind: str`, `model: type[AppBaseModel]`, `localize_vi: Localizer | None = None` (the localizer slot stays None here; task 2.1 fills it).
  - `register_panel(spec: PanelSpec) -> None` — raises on duplicate `kind` (a re-registration is a bug, not an override).
  - `get_panel(kind: str) -> PanelSpec | None` and `panel_kinds() -> tuple[str, ...]`.
  - Move `_gmaps_dir_url` OUT of base — it is route-specific; it belongs in `route.py`.

One module per kind, each carrying its own model(s), its presentation tables, and a `register_panel(...)` call at import time:
  - `route.py` — `RoutePanelEndpoint`, `RoutePanelLeg`, `RoutePanel`, `_gmaps_dir_url`
  - `weather.py` — `WeatherPanelCurrent`, `WeatherPanelDay`, `WeatherPanel`, `_COND_*`, `_condition`
  - `air_quality.py` — `AirQualityPanelPollutant`, `AirQualityPanelDay`, `AirQualityPanel`, `_AQI_BAND`, `_AQI_EMOJI`, `_AQI_ADVICE`, `_AQI_UNKNOWN_ADVICE`
  - `flights.py` — `FlightsPanelFlight`, `FlightsPanel`
  - `hotels.py` — `HotelsPanelHotel`, `HotelsPanel` (both `from_hotels` and `from_catalog`)
  - `places.py` — `PlacesPanelPlace`, `PlacesPanel`

Copy the class bodies and docstrings VERBATIM — no renames, no field changes, no "while I'm here" cleanups. The only edits are the import lines each module now needs.

`__init__.py` — imports all six submodules (this is what triggers registration; add a `# noqa: F401` or an explicit `__all__` so the ruff hook does not strip them, see the `ruff-on-edit-strips-unused-imports` learning) and re-exports the six `*Panel` classes plus the row models, so every existing `from app.streaming.panels import X` keeps resolving. Also re-export `register_panel` / `get_panel` / `panel_kinds` from `base`.

DELETE the `PanelKind = Literal[...]` alias: grep proves it has zero importers, and `panel_kinds()` is its live replacement. Note this in SUMMARY `### Deviations` (dead code inside the file being refactored).

Fix the one test that reaches for a module-private name: `tests/streaming/test_panel_localizer.py:105` imports `_AQI_ADVICE, _AQI_BAND` from `app.streaming.panels` — repoint it at `app.streaming.panels.air_quality`. Do NOT re-export private names from `__init__` to avoid this.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/streaming tests/tools tests/api/agent/test_stream_events.py -q</verify>
  <done>panels.py is gone; the package imports clean; every panel test passes with no assertion edited; `python -c "from app.streaming.panels import RoutePanel, WeatherPanel, AirQualityPanel, FlightsPanel, HotelsPanel, PlacesPanel, panel_kinds; print(panel_kinds())"` prints all six kinds.</done>
</task>
```

### Task 2.1 — Colocate `vi` localization with its panel; `localize_panel` dispatches via the registry

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/streaming/panel_localizer.py, apps/api/app/streaming/panels/base.py, apps/api/app/streaming/panels/weather.py, apps/api/app/streaming/panels/air_quality.py, apps/api/app/streaming/panels/places.py, apps/api/app/streaming/panels/hotels.py, apps/api/tests/streaming/test_panel_localizer.py</files>
  <action>Move each kind's `vi` translation next to the panel it translates, and turn `localize_panel`'s `if kind == …` chain into a registry lookup.

In `panels/base.py`: add the `Translator = Callable[[str], Awaitable[str]]` alias, the `_swap(value, table)` helper (moved verbatim from `panel_localizer`), and the `Localizer` alias — `Callable[[dict, Translator | None], Awaitable[None]]`. The localizer mutates the already-deep-copied dict IN PLACE and returns None; the copy/no-op policy stays in the façade so no panel module can get it wrong.

Move into the panel modules, verbatim, and pass them to `register_panel(...)` as `localize_vi`:
  - `weather.py` — `WEATHER_VI` + the `current`/`daily` description swap
  - `air_quality.py` — `AQI_CATEGORY_VI`, `AQI_ADVICE_VI` + the category/advice/forecast swap
  - `places.py` — `CATEGORY_VI` + the category swap and the awaited `translator(desc)` call, keeping the `try/except` + `logger.error("[PANEL_LOCALIZER] translate failed: %s", e)` behavior (an absent translator leaves the English description in place)
  - `hotels.py` — `AMENITY_VI` + the amenity swap
  Keep the parity comments that tie each table to its source of truth (WMO_CODES, `_AQI_BAND` keys, `CATEGORY_META`, seeded amenities) — the parity tests reference them.
  `route.py` / `flights.py` register no localizer (they have no bounded strings today) — `localize_vi=None`, which must behave exactly like the old `else` branch: deep-copy, localize nothing.

`panel_localizer.py` keeps its module path, its `localize_panel(kind, data, language, translator=None)` signature and its docstring contract, so `mapper.py` is untouched. Its body becomes: non-`vi` or non-dict `data` → return the SAME object unmodified (strict identity no-op — `tests/streaming/test_panel_localizer.py` asserts identity, not equality); otherwise `out = copy.deepcopy(data)`, look up `get_panel(kind)`, `await spec.localize_vi(out, translator)` when present, return `out`. Re-export `WEATHER_VI` / `AQI_CATEGORY_VI` / `AQI_ADVICE_VI` / `CATEGORY_VI` / `AMENITY_VI` is NOT wanted — update the parity tests to import each table from its panel module instead.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/streaming -q</verify>
  <done>`panel_localizer.py` contains no `if kind ==` chain and no `*_VI` table; every localizer test passes unchanged in its assertions (only imports move); `en` is still an identity no-op (`assert localize_panel(...) is data`).</done>
</task>
```

### Task 2.2 — Make the registry load-bearing: `panel_result` rejects an unknown kind

```xml
<task id="2.2" wave="2">
  <files>apps/api/app/tools/_base.py, apps/api/tests/tools/test_panel_result.py</files>
  <action>`panel_result(summary, *, kind: str, data)` currently accepts any string and no caller checks it, so a typo'd kind reaches the FE as an unrenderable panel. Validate it: look the kind up with `app.streaming.panels.get_panel(kind)` and raise `ValueError(f"unknown panel kind: {kind!r}")` when it is not registered — a programming error at the tool seam, not a runtime condition to swallow, so no domain exception and no logging fallback.

Import direction is safe: `app/tools/*` already imports from `app/streaming/panels` (5 tool modules do), and `app/streaming/panels/*` imports only from `app/schemas` + `app/services` — no cycle.

New `tests/tools/test_panel_result.py`: (a) each of the six registered kinds round-trips — `panel_result("s", kind=k, data={})` returns `("s", {"kind": k, "data": {}})`; (b) an unregistered kind raises `ValueError`; (c) the six kinds emitted by the real tools are exactly `set(panel_kinds())` — that last one is the drift guard between a tool and its panel module.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/tools -q</verify>
  <done>An unregistered kind raises `ValueError`; all six real tool kinds pass; no existing tool test changed.</done>
</task>
```

### Task 3.1 — Document the "add a panel" contract + full-suite proof

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/streaming/panels/__init__.py, specs/streaming-panels-split/SUMMARY.md</files>
  <action>Write the package docstring in `panels/__init__.py` as the how-to that replaces the old `panels.py` header: the `(summary, artifact)` / `{"kind", "data"}` contract, and a numbered "to add a panel kind" recipe — (1) create `panels/<kind>.py` with the projection model + `from_*` classmethod, (2) add its `vi` tables + an async `localize_vi(data, translator)` if it has bounded strings, (3) `register_panel(PanelSpec(kind=..., model=..., localize_vi=...))`, (4) import it in `__init__` — and state explicitly that nothing else needs editing (no `Literal`, no dispatch chain). Point at `specs/agent-side-panel` and `specs/min-57-side-panel-language` for the original designs.

Grep for and fix stale prose references to the old path (`app/streaming/panels.py`) left in docstrings/comments. Then fill in SUMMARY.md: `## What changed`, `### Deviations`, and the `### Verify` table (one row per command actually run).</action>
  <verify>cd apps/api &amp;&amp; ruff check app tests &amp;&amp; ../../.venv/bin/python -m pytest -q</verify>
  <done>Full BE suite green, ruff clean, SUMMARY.md `### Verify` rows filled from real runs.</done>
</task>
```

## 5. Risks

| Risk | Why it bites | Mitigation |
| --- | --- | --- |
| **Module ↔ package collision** | `panels.py` and `panels/` cannot coexist — a half-landed split leaves an ambiguous import that fails in a confusing way | Task 1.1 is atomic: the delete and the package land in one commit. Do not split it across waves. |
| **`ruff-on-edit` strips the `__init__` re-exports** | The submodule imports in `__init__.py` exist for their *side effect* (registration) and look unused ([[ruff-on-edit-strips-unused-imports]]) | Explicit `__all__` + `# noqa: F401`; the wave-1 `<verify>` catches it immediately if they vanish. |
| **`en` no-op degrades from identity to a copy** | `panel_localizer`'s contract is that a non-`vi` panel returns *the same object*, un-copied; a naive registry rewrite deep-copies first, then dispatches | Keep the language guard ahead of the deepcopy in the façade; the existing test asserts `is`, not `==`. |
| **Panel payload drift** | Any accidental field rename silently changes a client-visible SSE payload | Class bodies are copied verbatim; `tests/streaming/test_{flights,hotels,places}_panel.py` + `tests/api/agent/test_stream_events.py` assert the projections, and they must pass with **zero assertion edits**. If an assertion needs changing, the refactor broke the contract — stop. |
| **`risk-corroboration` hook flags `public-contract`** | The hook greps the staged diff; moving Pydantic models between files can look like contract surface ([[public-contract-hard-gate]]) | The lane is `normal` and the payload is provably unchanged (see above). If the hook blocks the commit, re-run with `RISK_WARN_CATEGORIES="public-contract"` — set it inline on the `git commit`, and note it in SUMMARY. |

## 6. Execution notes

- Route (per `/feature-intake`, `normal` lane): `/using-git-worktrees` → `/subagent-driven-development`.
  Branch off `v3` (`git switch -c refactor/streaming-panels-split`); PR targets `v3`, not `main`.
- Waves: 1 → (2.1 ‖ 2.2) → 3. Wave 2's two tasks have **zero file overlap** (2.1 owns
  `panel_localizer.py` + the panel modules; 2.2 owns `app/tools/_base.py` + a new test file), so
  they may run as parallel subagents in one message. Waves 1 and 3 are single-task.
- Stage and commit as separate commands (PreToolUse hook blocks `git add … && git commit …`).

## 7. Status Log

| Date | Event |
| --- | --- |
| 2026-07-12 | Intake done (`normal` / `high`); design fork resolved with the user (split + registry, imports preserved). Plan proposed. |
