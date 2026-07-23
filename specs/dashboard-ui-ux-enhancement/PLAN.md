---
slug: dashboard-ui-ux-enhancement
status: shipped
owner: minhtran
created: 2026-07-10
---

# BE `/dashboard` UI/UX Hardening — Slice 1 (a11y + data-safety + filter friction)

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development)
> to implement this plan task-by-task. Full research + rationale lives in
> `specs/dashboard-ui-ux-enhancement/RESEARCH.md` — read it before coding.

**Goal:** Ship the WCAG-AA accessibility fixes, the destructive-action safety fix, and
the filter-bar friction fixes for the server-rendered `/dashboard/*` (Jinja2) surface —
without a visual redesign and without breaking existing dashboard tests. This is
**Wave 1 + the safe subset of Wave 2** from `RESEARCH.md` §5.

**Architecture:** Pure front-end changes to `apps/api/app/templates/*.html` (HTML
semantics + inline CSS + vanilla JS) plus **one new hermetic render-smoke test**. No
router/service/repo/schema changes this slice (the agent-config dual-path collapse is
deferred — see Non-goals). The shared modal focus helper is added to `base.html` as a
tiny vanilla-JS `window.openDialog`/`window.closeDialog` and the four existing modals
(hotels, places, bookings, agent-config) are refactored to call it.

**Tech stack:** Jinja2 templates, vanilla JS (no framework), the existing Sunset
`--*` tokens in `base.html` `:root`, pytest via `fastapi.testclient.TestClient` (the
`client` fixture in `tests/conftest.py` seeds a temp SQLite DB).

**Conventions honored:** extend the design system, never route around it
(`apps/api/DESIGN.md`); no native `window.confirm`/`alert`/`prompt` (use the existing
`tpDialog`/`tpConfirm` in `base.html`); `prefers-reduced-motion` alternatives for any
new motion; surgical, minimum-diff per file. Run BE commands from `apps/api/`
(`CLAUDE.md`); the venv is the root `../../.venv`.

---

## 1. Motivation

`RESEARCH.md` reviewed all 18 `/dashboard` templates + the `base.html` shell against the
"Sunset Departures Board" design system and `PRODUCT.md`'s WCAG-AA target. The dashboard
is mature and well-crafted; the highest-value work is **interaction & accessibility
hardening**, not restyling. Four P1 themes surfaced:

1. **Modal focus management is absent** (hotels/places/bookings/agent-config) — no focus
   trap, no initial focus, no focus restore, no `inert` behind. WCAG 2.1.2 / 2.4.3 /
   2.4.7 fail for every keyboard/SR user.
2. **Destructive cancel-booking has no confirmation** — `bookings.html` POSTs
   `/bookings/{id}/cancel` + reloads on a single click, though a styled `tpConfirm`
   already exists in `base.html`.
3. **Filter controls are unlabeled & auto-submit traps the keyboard** — filter bars use
   sibling `<span class="fl">` not `<label>` (WCAG 4.1.2), and
   `onchange="this.form.submit()"` navigates away while a keyboard user arrows a
   `<select>`.
4. **One native `confirm()` survivor** — `agent_config_edit.html` still uses
   `onsubmit="return confirm(...)"`, violating the repo's no-native-dialog rule.

This slice fixes #1–#4 plus the cheap shell a11y wins (skip-link, `color-scheme`,
consistent `:focus-visible`) and the filter/clickable-row friction, touching each
template **once**.

## 2. Non-goals (this slice)

- **No agent-config dual-path collapse.** Removing/redirecting the standalone edit page
  breaks `test_edit_page_renders_for_known_agent` / `test_edit_page_unknown_agent_404`
  and needs the product decision in `RESEARCH.md` §7 Q1 (modal vs standalone). Deferred
  to a later slice. This slice only swaps its native `confirm()` → `tpConfirm`.
- **No router/service/repo/schema changes.** No `dashboard.py` edits.
- **No loading skeleton / streaming** for weather/AQ (P2-5) — that needs server-stream
  or JS-fetch plumbing; deferred. This slice adds only a retry link to the error block.
- **No P3 polish** (sticky FIDS header, "on time" pill, live-clock seconds, refresh
  chip, hotel distance chip, scroll-spy, topbar grouping) — deferred to a later slice.
- **No new JS test framework.** Modal focus / confirm behaviors are JS; re-runnable
  evidence is the render-smoke test + the manual keyboard/reduced-motion acceptance in
  the final task (per `plan-format.md`, manual UX checks belong at phase level).
- **No FE (`apps/web`) changes** — this is the BE dashboard only.

## 3. Success Criteria

Automated (re-runnable, exit 0):

- `tests/api/dashboard/test_dashboard_render.py` passes — every `/dashboard/*` route
  (landing / no-upstream variants) returns 200 with a key marker.
- `grep -R 'onchange="this.form.submit()"' app/templates` → **0** hits.
- `grep -R '<span class="fl"' app/templates` → **0** hits (every filter control is a
  `<label>`).
- `grep -R 'window.confirm\|window.alert\|window.prompt\|=confirm(\|=alert(\|=prompt(' app/templates` → **0** hits.
- `grep -R 'openDialog\|closeDialog' app/templates/base.html` → defined; and called in
  `hotels.html`, `places.html`, `bookings.html`, `agent_config.html`.
- `bookings.html` cancel handler calls `tpConfirm` before `fetch(.../cancel)`.
- `base.html` has a skip-link (`class="skip"`), `color-scheme: dark` in `:root`, and a
  shared `:focus-visible` rule covering `.tab/.fb-link/.explore a/.seg a/.version-pill/
  .toggle-chip/.back`.
- `cd apps/api && ../../.venv/bin/python -m pytest tests/ -q` fully green;
  `ruff check app scripts` clean.

Manual (phase-level acceptance, recorded in SUMMARY):

- Keyboard-only pass: Tab through each filter bar (no surprise navigation); open each
  modal with the keyboard, focus is trapped inside + moved to the first control, Esc
  closes and **focus returns to the triggering card/row**.
- `bookings.html` cancel opens the themed `tpConfirm`; Cancel aborts (no POST), OK
  cancels + reloads.


## 4. Decisions locked at planning (read before coding)

1. **Modal focus = one shared helper in `base.html`.** `window.openDialog(modal, opts)`
   + `window.closeDialog(m)` store `document.activeElement`, set `inert` + `aria-hidden`
   on `body > *` except the modal, move focus to `opts.initialFocus` (or first focusable),
   install a Tab trap + Esc handler, and restore focus on close. Every modal calls it.
   One mechanism, on-system, fixes C3 everywhere; avoids four divergent implementations.
2. **Touch each template once.** Each wave-2 task bundles that file's P1 + P2 fixes
   (labels + drop `onchange` + modal focus + de-nest + retry/confirm as applicable).
3. **`onchange=submit` removed everywhere; `.fb-btn` is the explicit submitter.** Every
   filter bar already has one. Single exception: the one-tap `.toggle-chip` filters
   (Recommended / Essential only) **keep** auto-submit — a checkbox toggle is unambiguous
   and the keyboard trap doesn't apply (it's not a multi-option `<select>`).
4. **Native `confirm()` → themed dialog only** in `agent_config_edit.html` (no path
   collapse). The standalone page keeps rendering + POSTing as today; only the JS guard
   changes (uses `tpDialog` with `danger:false` since a Save isn't destructive — see Risk
   "Themed confirm API"). Existing edit-page tests stay green.
5. **Clickable rows → single `<a>` keyboard target.** For FIDS rows (`.frow`) and the
   bookings ledger (`.brow`): drop `tabindex="0"` on the `<tr>`, keep the existing
   in-row link as the sole tab stop, and make the whole row a click/Enter shortcut that
   calls the link's `click()` (not `location.href`). Add an `aria-label` summarizing the
   row. Removes the double tab-stop + names the action.
6. **Hermetic render-smoke test** GETs each route's **landing / no-upstream variant**
   (e.g. `/dashboard/weather` with no `?city`) so it never hits Open-Meteo and stays
   <60s on SQLite. This is the per-task automated verify for templates that lack a
   dedicated dashboard test.

## 5. Tasks

### Task 1.1 — base.html: shared modal focus helper + shell a11y

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/templates/base.html</files>
  <action>Add four things, all in base.html:
(1) In :root add `color-scheme: dark;` (shell is dark; makes native <select>/<input type=date>/<input type=search>/scrollbars render in dark UA chrome — FE globals.css:102 already does this for apps/web).
(2) Shared focus-visible rule using the existing --ring token: `:where(.tab,.fb-link,.explore a,.seg a,.version-pill,.toggle-chip,.back):focus-visible{outline:none;box-shadow:var(--ring);}`.
(3) Skip-link as first child of <body>: `<a class="skip" href="#main">Skip to content</a>` + `id="main"` on the `.wrap` div; CSS `.skip{position:absolute;left:-9999px;top:0;z-index:var(--z-modal)} .skip:focus{left:8px;top:8px;background:var(--panel);color:var(--ink);padding:8px 12px;border-radius:var(--radius-sm);border:1px solid var(--accent)}`.
(4) Modal focus helper as a <script> next to the existing tpDialog script (~line 850). Define `window.openDialog(modal,opts)`: store `document.activeElement`; set `inert`+`aria-hidden` on `body>*` except the modal and `.skip`; add `.show` + `aria-hidden=false`; lock `body.overflow`; focus `opts.initialFocus` (selector or el) or first focusable; add a keydown listener that Esc->closeDialog and Tab/Shift+Tab wraps within the modal. Define `window.closeDialog(modal)`: remove `.show`+`aria-hidden=true`; unlock overflow; remove listener; clear `inert`; restore focus to the stored trigger. No animation of its own (existing .show transitions + the global prefers-reduced-motion block at base.html:749 handle motion). No native confirm/alert/prompt.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('base.html'); print('parse ok')" && grep -q 'color-scheme: dark' app/templates/base.html && grep -q 'class=\"skip\"' app/templates/base.html && grep -q 'window.openDialog' app/templates/base.html</verify>
  <done>base.html parses; color-scheme:dark present; skip-link present; window.openDialog/closeDialog defined; shared :focus-visible rule present.</done>
</task>
```

### Task 1.2 — Hermetic render-smoke test for every /dashboard route

```xml
<task id="1.2" wave="1">
  <files>apps/api/tests/api/dashboard/__init__.py, apps/api/tests/api/dashboard/test_dashboard_render.py</files>
  <action>Create tests/api/dashboard/__init__.py (empty). Create test_dashboard_render.py using the session `client` fixture (tests/conftest.py — temp SQLite, seeded). One test function per route, each GETs the landing/no-upstream variant and asserts HTTP 200 + one key marker — hermetic (never hits Open-Meteo): /dashboard -> 'Travel Planner'; /dashboard/flights -> 'board-head'; /dashboard/flights/search -> 'Search flights'; /dashboard/hotels -> 'hotel-grid'; /dashboard/places -> 'place-grid'; /dashboard/tips -> 'picker'; /dashboard/visa -> 'vbook'; /dashboard/weather (no ?city) -> 'filter-bar'; /dashboard/air-quality (no ?city) -> 'filter-bar'; /dashboard/bookings -> 'ledger'; /dashboard/agent-config -> 'agent-grid'; /dashboard/prompts -> 'prompt-workspace'. Separate functions so a failure points at the exact page. No network stubs needed for the no-city weather/aq variants.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py -q</verify>
  <done>All ~12 route render-smoke tests pass on the temp SQLite client; <60s.</done>
</task>
```

### Wave 2 — per-template hardening (parallel; each task a distinct file; depends on 1.1 + 1.2)

### Task 2.1 — board.html: label filters, drop onchange trap, single row target

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/templates/board.html</files>
  <action>(1) Convert each `.fg` filter group from `<span class="fl">Label</span><select…>` to `<label class="fg"><span class="fl">Label</span><select…></label>` (keeps the exact look; now SR-heard). (2) Remove `onchange="this.form.submit()"` from the airport + date selects (board.html:18,29); the existing `.fb-btn` "View" (board.html:32) is the submitter. (3) Clickable row: remove `tabindex="0"` from `.frow` (board.html:70); keep the flight-number `<a>` (board.html:85) as the sole tab stop and give it `aria-label="Flight {{ row.flight_number }} — {{ row.airport.city if row.airport else row.airport_code }}"`. Change the row click handler (board.html:110-118) to call the `<a>`'s `click()` instead of `location.href`, and drop the row keydown handler (the link handles Enter). (4) Remove the bespoke `.frow:focus-visible` rule (board.html:98) — the shared base.html rule from 1.1 now covers focus. No visual change.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('board.html'); print('parse ok')" && ! grep -q 'onchange="this.form.submit()"' app/templates/board.html && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py -q</verify>
  <done>board.html parses; no onchange=submit; filters are <label>; single <a> row target with aria-label; render-smoke green.</done>
</task>
```

### Task 2.2 — hotels.html: modal focus + label filters + drop onchange + de-nest card button

```xml
<task id="2.2" wave="2">
  <files>apps/api/app/templates/hotels.html</files>
  <action>(1) Modal focus: in openModal (hotels.html:352) replace the manual `.show`/`aria-hidden`/`overflow` lines with `window.openDialog(modal,{initialFocus:'#hm-name'})`; in closeModal (hotels.html:394) replace with `window.closeDialog(modal)`. Remove the duplicate Esc keydown (hotels.html:411-413) — openDialog owns Esc. (2) Convert each `.fg` to `<label class="fg">` (search/city/sort). (3) Remove `onchange="this.form.submit()"` from city + sort selects (hotels.html:35,45); the `.fb-btn` "Search" (hotels.html:55) submits. (4) Card: keep `<article class="hotel-card" role="button" tabindex="0">` (hotels.html:80) but add `aria-haspopup="dialog"` + `aria-label="{{ hotel.name }} — {{ hotel.city }}"` so SR announces it; the modal focus helper handles the rest. (No nested interactive child in hotels, so no stopPropagation hack needed.) No visual change.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('hotels.html'); print('parse ok')" && ! grep -q 'onchange="this.form.submit()"' app/templates/hotels.html && grep -q 'openDialog' app/templates/hotels.html && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py -q</verify>
  <done>hotels.html parses; no onchange=submit; filters are <label>; modal uses openDialog/closeDialog; card has aria-label; render-smoke green.</done>
</task>
```

### Task 2.3 — places.html: modal focus + label filters + drop onchange + de-nest save + native city select + _explore

```xml
<task id="2.3" wave="2">
  <files>apps/api/app/templates/places.html</files>
  <action>(1) Modal focus: in openModal (places.html ~470) use `window.openDialog(modal,{...})`; closeModal uses `window.closeDialog(modal)`; remove the duplicate Esc keydown (places.html:506-508). (2) Convert each `.fg` to `<label class="fg">` (category/min_rating/price_level/sort). (3) Remove `onchange="this.form.submit()"` (places.html:37,47,57,78); the form currently relies on onchange, so add a `.fb-btn` "Apply" submit button before the first `.fb-sep`. Keep the `.toggle-chip` Recommended auto-submit (Decision #3). (4) De-nest the save button: the `.pc-save` `＋` (places.html:566) `stopPropagation`s inside the card click — keep it (genuine second action) but add `aria-label="Save {{ name }} to trip"`. Keep the card as dialog opener: `role="button"` + `tabindex="0"` + `aria-haspopup="dialog"` + `aria-label="{{ name }} — {{ city }}"`. (5) Replace the hand-rolled city combobox (places.html:23-33 `#city-input`+`#city-dropdown`) with a native `<select name="city">` listing "All cities" + cities, matching every other surface for consistency + a11y; remove the autocomplete JS. (6) Add `{% from "_explore.html" import explore %}` (top, next to the existing import) and render `{{ explore(selected_city or '', 'places') }}` after the grid — places currently lacks the Explore strip. No bento-grid visual regression.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('places.html'); print('parse ok')" && ! grep -q 'onchange="this.form.submit()"' app/templates/places.html && grep -q 'openDialog' app/templates/places.html && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py tests/api/place/test_places.py -q</verify>
  <done>places.html parses; no onchange=submit; filters are <label>; city is a native <select>; modal uses openDialog/closeDialog; _explore strip present; render-smoke + existing places tests green.</done>
</task>
```

### Task 2.4 — tips.html: label filters + drop onchange

```xml
<task id="2.4" wave="2">
  <files>apps/api/app/templates/tips.html</files>
  <action>(1) Convert each `.fg` (country/city/category) to `<label class="fg">`. (2) Remove `onchange="this.form.submit()"` (tips.html:35,45,55); add a `.fb-btn` "Apply" submit button before the `.fb-sep` (the form currently relies on onchange). Keep the `.toggle-chip` "Essential only" auto-submit (Decision #3). No other change.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('tips.html'); print('parse ok')" && ! grep -q 'onchange="this.form.submit()"' app/templates/tips.html && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py tests/api/info/test_tips.py -q</verify>
  <done>tips.html parses; no onchange=submit; filters are <label>; render-smoke + existing tips tests green.</done>
</task>
```

### Task 2.5 — visa.html: label filters + drop onchange

```xml
<task id="2.5" wave="2">
  <files>apps/api/app/templates/visa.html</files>
  <action>(1) Convert the `.fg` (country) to `<label class="fg">`. (2) Remove `onchange="this.form.submit()"` (visa.html:22); add a `.fb-btn` "Apply" submit button (the form currently relies on onchange). No other change.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('visa.html'); print('parse ok')" && ! grep -q 'onchange="this.form.submit()"' app/templates/visa.html && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py tests/api/info/test_visa.py -q</verify>
  <done>visa.html parses; no onchange=submit; filter is <label>; render-smoke + existing visa tests green.</done>
</task>
```

### Task 2.6 — weather.html: label filters + drop onchange + retry link on error

```xml
<task id="2.6" wave="2">
  <files>apps/api/app/templates/weather.html</files>
  <action>(1) Convert the `.fg` (city/days) to `<label class="fg">`. (2) Remove `onchange`-style auto-submit if present (the weather form uses a `.fb-btn` "Check weather" already — just ensure no `onchange=submit` remains). (3) In the error block (weather.html:74-75), add a retry link: `<a class="empty-hint" href="/dashboard/weather?city={{ query_city|urlencode }}&days={{ days }}">↻ Try again</a>` so a failed upstream lookup offers a one-click retry (no new state — just a same-URL GET). No loading skeleton this slice (Non-goal).</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('weather.html'); print('parse ok')" && ! grep -q 'onchange="this.form.submit()"' app/templates/weather.html && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py -q</verify>
  <done>weather.html parses; no onchange=submit; filters are <label>; error block has a retry link; render-smoke green.</done>
</task>
```

### Task 2.7 — air_quality.html: label filters + drop onchange + retry link + AA dial contrast

```xml
<task id="2.7" wave="2">
  <files>apps/api/app/templates/air_quality.html</files>
  <action>(1) Convert the `.fg` (city) to `<label class="fg">`. (2) Ensure no `onchange=submit` remains (the form uses a `.fb-btn` "Check air quality"). (3) Add a retry link in the error block mirroring weather.html: `<a class="empty-hint" href="/dashboard/air-quality?city={{ query_city|urlencode }}">↻ Try again</a>`. (4) AA spot-check/fix the AQI dial value: the `.aq-dial-val` uses `color: rgb(var(--cglow))` (colored number on a colored gradient). If the "Good" green end fails 4.5:1 on the gradient, render the number in `var(--ink)` and keep color only on the ring/glow (color stays redundant with the category label + AQI number, so this honors "color not alone"). Verify contrast by eye against each of the 6 bands; only change the number color if a band fails.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('air_quality.html'); print('parse ok')" && ! grep -q 'onchange="this.form.submit()"' app/templates/air_quality.html && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py -q</verify>
  <done>air_quality.html parses; no onchange=submit; filter is <label>; error block has a retry link; dial value AA-safe (ink or verified band colors); render-smoke green.</done>
</task>
```

### Task 2.8 — bookings.html: confirm cancel via tpConfirm + modal focus + label filters + single row target (P1-2)

```xml
<task id="2.8" wave="2">
  <files>apps/api/app/templates/bookings.html</files>
  <action>(1) DATA-SAFETY (P1-2): the cancel handler (bookings.html:268-278) currently POSTs `/bookings/{id}/cancel` then `location.reload()` on a single click. Wrap it in the existing themed confirm: before the fetch, call `window.tpConfirm('Cancel booking?', 'This cancels booking ' + current.code + '. This cannot be undone.', 'Cancel booking').then(function(ok){ if(!ok) return; /* existing disable+POST+reload body */ })`. tpConfirm(title, message, okLabel) is defined at base.html:889 and renders a danger-styled OK (correct for a destructive cancel). On cancel-abort, do nothing (leave the modal open). (2) Modal focus: in open() (bookings.html:219) replace the manual `.show`/`aria-hidden`/`overflow` with `window.openDialog(modal,{initialFocus:'#bk-copy'})`; in close() (bookings.html:242) use `window.closeDialog(modal)`; remove the duplicate Esc keydown (bookings.html:255-257). (3) Convert the `.fg` (search/type/sort) to `<label class="fg">`. (4) Remove `onchange="this.form.submit()"` (bookings.html:21,30); the `.fb-btn` "Search" (bookings.html:38) submits. (5) Single row target: remove `tabindex="0"` from `.brow` (bookings.html:80); the row opens the modal on click — give the row an `aria-label` via a visually-hidden link or keep the click opener but add `role="button"` + `tabindex="0"` + `aria-label="Booking {{ booking.confirmation_code }} — {{ booking.customer_name }}"` ONLY if there's no in-row link. Since the ledger row has no in-row `<a>`, keep `tabindex="0"` + add `role="button"` + `aria-label` (the modal is the destination; this is the one justified exception to Decision #5). No visual change.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('bookings.html'); print('parse ok')" && ! grep -q 'onchange="this.form.submit()"' app/templates/bookings.html && grep -q 'tpConfirm' app/templates/bookings.html && grep -q 'openDialog' app/templates/bookings.html && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py -q</verify>
  <done>bookings.html parses; cancel wrapped in tpConfirm; modal uses openDialog/closeDialog; filters are <label>; no onchange=submit; row has role+aria-label; render-smoke green.</done>
</task>
```

### Task 2.9 — agent_config.html: modal focus (trap/restore) + confirm-dialog stacking focus

```xml
<task id="2.9" wave="2">
  <files>apps/api/app/templates/agent_config.html</files>
  <action>(1) The edit modal already focuses `#am-provider` on open (agent_config.html:390) but has no trap/restore. Refactor openModal to use `window.openDialog(modal,{initialFocus:'#am-provider'})` and closeModal to use `window.closeDialog(modal)`; remove the now-redundant manual `.show`/`aria-hidden`/`overflow` + the standalone Esc handler (agent_config.html:407-411) — BUT keep the Esc-stacking guard logic: when the confirm dialog `#confirm-modal` is open, Esc should close the confirm, not the edit modal. Implement that by giving `#confirm-modal` its own `openDialog` call (see below) so the helper's Esc only closes the top-most dialog it opened. (2) The styled save-confirm dialog `#confirm-modal` (agent_config.html:439-461): refactor openConfirm to `window.openDialog(confirmModal,{initialFocus:'#cm-confirm'})` and closeConfirm to `window.closeDialog(confirmModal)` — note closeConfirm must NOT unlock `body.overflow` while the edit modal is still open behind it; handle this by having `closeDialog` only clear overflow if no other `.show` modal remains (add to the base helper OR check in closeConfirm: `if(document.querySelector('.agent-modal.show, .hm-dialog.show, .bk-dialog.show, #cmdk.show')){keep overflow hidden}`). On confirm OK, `closeConfirm()` then `form.submit()`. (3) No filter-bar changes (agent_config has no filter bar). No markup ids removed (tests assert `id="agent-modal"`, `id="agent-form"`, `id="am-enabled"`, `id="am-enabled-marker"`, `data-agent`, `data-enabled` — keep all).</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('agent_config.html'); print('parse ok')" && grep -q 'openDialog' app/templates/agent_config.html && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py tests/api/agent_config/test_agent_config_dashboard.py -q</verify>
  <done>agent_config.html parses; edit + confirm modals use openDialog/closeDialog; focus trap/restore + stacking handled; all existing agent-config dashboard tests green.</done>
</task>
```

### Task 2.10 — agent_config_edit.html: replace native confirm() with themed dialog (P1-4, no path collapse)

```xml
<task id="2.10" wave="2">
  <files>apps/api/app/templates/agent_config_edit.html</files>
  <action>Remove the native `onsubmit="return confirm('Save config for {{ agent_name }}? This changes the live agent model.');"` (agent_config_edit.html:30). Replace with a submit handler that calls the existing themed dialog: add a small <script> that, on form submit, `e.preventDefault()` then `window.tpDialog({ title: 'Save config for {{ agent_name }}?', message: 'This changes the live agent model. It takes effect on the next agent run.', input: false, okLabel: 'Save', danger: false }).then(function(ok){ if(ok) form.submit(); })`. Use `tpDialog` directly (NOT `tpConfirm`) because `tpConfirm` hardcodes `danger:true` (base.html:889) which would wrongly style a non-destructive Save as danger-red; `tpDialog` (base.html:852) accepts `okLabel` + `danger`. The form still POSTs to `/dashboard/agent-config/{{ agent_name }}` exactly as before; only the JS guard changes. No markup/ids removed (tests assert the page renders 200 + 'planner' + the fields — all kept). Do NOT collapse the dual edit path (Non-goal).</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('app/templates')).get_template('agent_config_edit.html'); print('parse ok')" && ! grep -q 'return confirm(' app/templates/agent_config_edit.html && grep -q 'tpDialog' app/templates/agent_config_edit.html && ../../.venv/bin/python -m pytest tests/api/dashboard/test_dashboard_render.py tests/api/agent_config/test_agent_config_dashboard.py -q</verify>
  <done>agent_config_edit.html parses; no native confirm(); uses tpDialog (non-danger); existing edit-page tests (200 + 404 + POST 303) green.</done>
</task>
```

### Wave 3 — slice gate (depends on all wave-2 tasks)

### Task 3.1 — Full-suite gate + manual UX acceptance + SUMMARY

```xml
<task id="3.1" wave="3">
  <files>specs/dashboard-ui-ux-enhancement/SUMMARY.md</files>
  <action>Run the full BE suite + lint, then perform the manual keyboard + reduced-motion acceptance and record results in SUMMARY.md. SUMMARY must list: (a) each task completed + its verify result; (b) the manual pass results — Tab through each filter bar (no surprise nav), open/close each modal via keyboard (focus trapped + restored to trigger), bookings cancel opens tpConfirm (Cancel aborts, OK cancels+reloads), prefers-reduced-motion shows no stuck animations; (c) any deviations from the plan; (d) carried-forward work (deferred: dual-path collapse, loading skeletons, P3 polish). If any check fails, do NOT mark done — fix and re-run.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/ -q && ../../.venv/bin/ruff check app scripts && grep -Rc 'onchange="this.form.submit()"' app/templates | awk -F: '{s+=$2} END{exit (s>0)}' && ! grep -RqE 'window.confirm|window.alert|window.prompt|=confirm\(|=alert\(|=prompt\(' app/templates</verify>
  <done>Full pytest suite green; ruff clean; zero onchange=submit remaining; zero native confirm/alert/prompt remaining; SUMMARY.md written with manual-pass results.</done>
</task>
```

## 6. Risks

- **Modal helper `inert` + stacked dialogs (Task 2.9).** The agent-config edit modal
  opens a confirm dialog on top. `openDialog` sets `inert` on `body>*` except the dialog;
  when the confirm opens, the edit modal is a sibling and would be inerted (correct —
  confirm is on top), but `closeDialog` must not unlock `body.overflow` while the edit
  modal is still open. Mitigation: `closeDialog` only clears `overflow` if no other
  `.show` modal remains. This is the trickiest task; test the stacking by hand in the
  acceptance pass.
- **Themed confirm API (confirmed).** `tpConfirm(title, message, okLabel)` (base.html:889)
  hardcodes `danger:true` — use it ONLY for destructive actions (bookings cancel, Task 2.8).
  For the non-destructive agent-config Save (Task 2.10) call `tpDialog({title, message,
  input:false, okLabel, danger:false})` directly so the OK button isn't red. Both return a
  `Promise<bool>`. No helper changes needed.
- **Places city `<select>` regression (Task 2.3).** Replacing the hand-rolled combobox
  with a native `<select>` changes the filter UX (no free-text autocomplete). The
  existing `tests/api/place/test_places.py` may assert the old `#city-input`/`#city-dropdown`
  markup — if so, update those assertions in the same task. Run that test file in verify.
- **No JS unit tests.** Modal focus, the Tab trap, and the confirm guards are JS
  behaviors with no automated unit coverage in this stack. The render-smoke proves the
  pages render; the manual keyboard/reduced-motion pass (Task 3.1) is the behavioral
  evidence. This is acceptable per `plan-format.md` (manual UX checks at phase level) but
  must actually be performed, not skipped.
- **`color-scheme: dark` on Nightfall.** Both Sunset and Nightfall are dark, so
  `color-scheme: dark` is correct for both; no per-theme override needed. (If a light
  theme is ever added, revisit.)
- **Wave-2 file overlap.** Verified zero `<files>` overlap across 2.1–2.10 (each is one
  distinct template; 2.9=agent_config.html, 2.10=agent_config_edit.html — distinct).
  Safe to run in parallel. All depend on 1.1 (helper) + 1.2 (smoke test).

## 7. Status Log

- 2026-07-10 — Research complete (`RESEARCH.md`); PLAN drafted on branch
  `feat/dashboard-ui-ux-enhancement` (off `v3`). Status: **proposed**.
- 2026-07-10 — **Implemented & verified.** All 13 tasks complete (status: **shipped**).
  `tests/api` 782 passed; `tests/agents`+`tests/eval` 162 passed; `tests/{core,tools,
  memory,mcp,streaming,prompts,architecture,infra,db,scripts}` 332 passed / 5
  pre-existing env-sensitive failures (OPENAI_API_KEY set in shell + routing offline;
  none touch templates). `ruff` clean. Grep gates green (only 2 `onchange=submit` =
  documented toggle-chip exceptions; 0 real native dialogs). See `SUMMARY.md`.
  Deferred: agent-config dual-path collapse (needs RESEARCH.md §7 Q1 decision),
  loading skeletons, P3 polish.

- `prefers-reduced-motion` pass: no stuck/half-finished animations; modals still usable.
