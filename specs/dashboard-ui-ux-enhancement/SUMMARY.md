# SUMMARY — BE `/dashboard` UI/UX Hardening (Slice 1)

> Branch: `feat/dashboard-ui-ux-enhancement` (off `v3`).
> Plan: `specs/dashboard-ui-ux-enhancement/PLAN.md` · Research: `RESEARCH.md`.
> Scope: a11y + data-safety + filter-friction hardening for the server-rendered
> `/dashboard/*` (Jinja2) surface. No visual redesign; no router/service changes.

## What shipped

All 13 plan tasks completed. Every `/dashboard` template touched once.

| Task | File | Outcome | Verify |
|---|---|---|---|
| 1.1 | `base.html` | `color-scheme:dark`; skip-link + `id="main"`; shared `:focus-visible` ring; `openDialog`/`closeDialog` modal focus helper (trap + initial focus + restore + `inert` + stacked-dialog guard) | parse ok; markers present |
| 1.2 | `tests/api/dashboard/test_dashboard_render.py` | 12 route render-smoke tests (hermetic, no Open-Meteo) | 12 passed |
| 2.1 | `board.html` | `<label>` filters; dropped `onchange=submit`; single `<a>` row target + `aria-label` | green |
| 2.2 | `hotels.html` | `<label>` filters; dropped `onchange`; modal → `openDialog`; card `aria-haspopup`+`aria-label` | green |
| 2.3 | `places.html` | `<label>` filters; native city `<select>` (removed combobox + CSS/JS); modal → `openDialog`; card aria; Apply btn | 97 passed |
| 2.4 | `tips.html` | `<label>` filters; dropped `onchange` (kept country→city clear); Apply btn | 37 passed |
| 2.5 | `visa.html` | `<label>` filter; dropped `onchange`; Apply btn | 24 passed |
| 2.6 | `weather.html` | `<label>` filters; retry link on error | green |
| 2.7 | `air_quality.html` | `<label>` filter; retry link on error | green |
| 2.8 | `bookings.html` | **P1-2: cancel wrapped in `tpConfirm`**; modal → `openDialog`; `<label>` filters; row `role`+`aria-label` | green |
| 2.9 | `agent_config.html` | edit + confirm modals → `openDialog`/`closeDialog`; focus trap/restore + stacking; duplicate Esc removed | 28 passed |
| 2.10 | `agent_config_edit.html` | native `confirm()` → themed `tpDialog` (`danger:false`); form POST unchanged | 28 passed |

## Automated gate results

- **`tests/api` (all endpoint + dashboard tests): 782 passed.** This bucket contains
  every dashboard render test + all router/service behavior — fully green.
- **`tests/{core,tools,memory,mcp,streaming,prompts,architecture,infra,db,scripts}`:
  332 passed, 5 failed.** The 5 failures are **pre-existing and environment-sensitive,
  not caused by these changes** — none reference any template/dashboard code:
  - `test_config_llm.py::test_llm_defaults_require_no_key` + `test_langfuse_disabled_by_default`
    + `test_embeddings.py::test_get_embeddings_fake_without_key`: fail because
    `OPENAI_API_KEY` is set in the local shell (tests assert it's `None`).
  - `test_routing_tools.py::test_get_city_route_offline_estimate` +
    `test_get_route_between_places_offline_estimate`: routing offline-estimate
    (env/ORS-key or precision sensitive).
  - Confirmed via `grep`: none reference `dashboard`/`templates`/`TemplateResponse`/
    `base.html`. They fail identically on the `v3` base.
- **`tests/agents` + `tests/eval`: 162 passed.** (LLM/agent tests on `FakeLLM`; do not
  touch templates.)
- **`ruff check app scripts`: All checks passed.**
- **Grep gates:**
  - `onchange="this.form.submit()"` → only 2 hits, both documented `.toggle-chip`
    exceptions (places "Recommended", tips "Essential only" — Plan Decision #3).
  - Real native `confirm()`/`alert()`/`prompt()` calls → **0** (remaining matches are
    code comments in `agent_config.html` describing the styled replacement).
  - `openDialog`/`closeDialog` → defined in `base.html`; called in `hotels.html`,
    `places.html`, `bookings.html`, `agent_config.html` (+ confirm dialog).

## Manual acceptance (to perform in browser on `make dev`)

JS behaviors (modal focus, Tab trap, confirm guards) have no JS unit coverage in this
stack; the render-smoke proves pages render; these checks are the behavioral evidence.

- [ ] **Keyboard filter bars:** Tab through each — no surprise navigation; toggle-chips
      still submit on toggle.
- [ ] **Modal focus:** open each modal via keyboard — focus moves to first control, Tab
      wraps inside, Esc closes and **focus returns to the triggering card/row**.
- [ ] **Bookings cancel:** opens themed `tpConfirm` (red OK); Cancel aborts (no POST),
      OK cancels + reloads.
- [ ] **Agent-config save (modal):** styled confirm stacks on edit modal; Esc closes the
      confirm (not the edit modal); Cancel returns focus to edit modal; Save POSTs.
- [ ] **Agent-config save (standalone page):** opens `tpDialog` (non-red OK); Save POSTs,
      Cancel aborts.
- [ ] **`prefers-reduced-motion`:** no stuck animations; modals usable; skip-link works.
- [ ] **Skip-link:** Tab from URL bar → "Skip to content"; Enter jumps to `#main`.

## Deviations from the plan

- **`_explore` in places:** plan assumed places lacked it; on re-read it was already
  rendered (`{{ explore(selected_city, 'places') }}`). Sub-item satisfied by existing code.
- **AQI dial AA contrast (Task 2.7):** dial value uses `rgb(var(--cglow))` on a gradient.
  Left as-is this slice (color redundant with category label + AQI number, per DESIGN.md
  "color not alone"). A per-band AA spot-check is carried forward as P3; no regression
  introduced.

## Carried forward (deferred — RESEARCH.md §5 Wave 3 + §7)

- **Agent-config dual-path collapse** (modal vs standalone) — needs RESEARCH.md §7 Q1
  decision; would break `test_edit_page_renders_for_known_agent`.
- **Loading skeleton / streaming** for weather/AQ (P2-5) — needs server-stream plumbing.
- **P3 polish:** sticky FIDS `<thead>`, "on time" micro-pill, live-clock seconds,
  "updated · refresh" chip, hotel distance-to-center chip, scroll-spy, topbar grouping,
  home itinerary live counts.
- **AQI dial per-band AA spot-check** (verify, not assumed broken).

| 3.1 | this file | full-suite gate + grep gates | see below |
