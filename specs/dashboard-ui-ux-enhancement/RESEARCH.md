# BE `/dashboard` — UI/UX Deep Research & Enhancement Proposal

> Status: **research + proposal** (pre-PLAN). Research-only — no code was changed.
> Scope: all 18 Jinja2 templates under `apps/api/app/templates/` served at
> `/dashboard/*`, the shell in `base.html`, and the handlers in
> `app/routers/dashboard.py` + `app/routers/dashboard_prompts.py`.
> Design system of record: `apps/api/DESIGN.md` ("Sunset Departures Board") +
> `apps/api/PRODUCT.md`. Tokens live in `app/templates/base.html` `:root`.

---

## 0. TL;DR

The dashboard is a **mature, genuinely well-crafted** dark "Sunset Departures Board"
system — strong metaphor, real color-coding discipline, tabular numerics, a ⌘K
palette, dual themes, view transitions, and tasteful motion with reduced-motion
fallbacks. It is *not* a slop dashboard and does not need a redesign.

The highest-value work is therefore **not visual restyling** but **interaction &
accessibility hardening**, plus a handful of **information-density and
state-completeness** gaps. The four P1 themes:

1. **Modal/dialog focus management is absent** (hotels, places, bookings, agent-config)
   — no focus trap, no initial focus, no focus restore, no `inert` on the page behind.
   WCAG 2.1.2 / 2.4.3 / 2.4.7 fail; affects every keyboard/SR user.
2. **A destructive action has no confirmation** — `bookings.html` cancel POSTs +
   reloads on a single click, though a styled `tpConfirm` already exists in `base.html`.
3. **Filter controls are unlabeled & auto-submit traps the keyboard** — filter bars use
   sibling `<span class="fl">` not `<label>`, and `onchange="this.form.submit()"`
   navigates away while a keyboard user arrows a `<select>`.
4. **One native `confirm()` survivor + dual edit paths** — `agent_config_edit.html`
   still uses `onsubmit="return confirm(...)"`, and agent config has two non-canonical
   edit surfaces (modal + standalone page).

Everything else is P2/P3 polish + density that extends — never routes around — the
existing system.

---

## 1. Method

- Direct read of every template (`base.html`, `index.html`, `board.html`,
  `search.html`, `flight_detail.html`, `hotels.html`, `places.html`, `tips.html`,
  `visa.html`, `weather.html`, `air_quality.html`, `bookings.html`,
  `agent_config.html`, `agent_config_edit.html`, `prompt_detail.html`,
  `prompt_diff.html`, `_prompt_sidebar.html`, `_explore.html`).
- Direct read of `app/routers/dashboard.py` + `dashboard_prompts.py` (all handlers +
  `TemplateResponse` context) and `apps/api/DESIGN.md` + `PRODUCT.md`.
- Parallel per-surface deep dives (flights / discovery / live-ledger / ops-config).
- Cross-cutting analysis of the shared shell (`base.html`).

All findings cite **file:line or class/token**. Severity: **P1** major usability/a11y
defect or data-safety risk · **P2** moderate friction/inconsistency · **P3** polish.
Proposals stay within Jinja2 + vanilla JS + the Sunset token set.

---

## 2. What's working well (keep, don't touch)

- **Metaphor is earned.** The FIDS board (`board.html`), the boarding-pass with
  die-cut perforation (`flight_detail.html`), the visa "stamp wall" (`visa.html`),
  and the AQI dial (`air_quality.html`) read as credible travel product.
- **Color-coding discipline.** Status remarks are always labeled pills; hotel/place/
  tip/visa carry per-topic `--c` hues paired with an emoji; AQI uses the EPA 6-band
  ramp *redundant with the label + number* — color never carries meaning alone.
- **Tabular figures** on every compared number (times, prices, durations, IDs, ratings).
- **Cross-cutting chrome is real:** ⌘K palette (`#cmdk`/`PAGES`), Sunset⇄Nightfall
  switch with pre-paint apply (`base.html:767-774`), page-load progress bar
  (`base.html:707-735`), `@view-transition` (`:740-747`), `TripStore` localStorage
  checklists (`:781-848`), themed `tpDialog`/`tpPrompt`/`tpConfirm` (`:850-889`).
- **Empty states** are friendly + consistent (`.empty`/`.empty-ico`/`.empty-hint`).
- **`prefers-reduced-motion`** honored globally (`base.html:749-765`) + per-surface.
- **Responsive** breakpoints (900/640/400) with mobile topbar horizontal scroll.


---

## 3. Cross-cutting findings (shared shell — `base.html`)

Cheapest, highest-leverage fixes; affect every page.

| # | Finding | Evidence | Impact | Sev |
|---|---|---|---|---|
| C1 | **No skip-link** to main content; `.wrap` has no `id`/`role="main"`. | `base.html` `<body>`. | Keyboard users tab through all 10+ nav tabs every page load. | P2 |
| C2 | **`color-scheme` not declared** on the dark shell (FE `globals.css:102` does set it). | `base.html` `:root`. | Native `<select>`/`<input type=date>`/`<input type=search>`/scrollbars render *light* UA chrome on some browsers → clash + poor contrast inside dark panels. | P2 |
| C3 | **Modals lack focus management.** Hotels/places/bookings/agent modals toggle `.show`+`aria-hidden`+`body.overflow` only — no initial focus, no trap, no restore, no `inert` on siblings. | `hotels.html:389-392`, `places.html:484-486`, `bookings.html:238-240`, `agent_config.html:387-389`. | Keyboard/SR users escape behind the dialog; focus lost on close. WCAG 2.1.2/2.4.3/2.4.7. | **P1** |
| C4 | **`:focus-visible` inconsistent.** `--ring` token exists but most primitives rely on UA outlines or none; `.explore a`, `.fb-link`, `.tab`, `.seg a`, `.version-pill`, `.toggle-chip` have no explicit focus ring. | `base.html:594-600` (hover only); `board.html:98` adds a bespoke per-page rule. | Keyboard focus often invisible on links/chips. | P2 |
| C5 | **14 flat items in one `.topbar`** (10 tabs + ⌘K + theme + API Docs + spacer), no grouping. | `base.html:899-917`. | Cognitively flat despite the data grouping the home page already implies. | P3 |
| C6 | **`onchange="this.form.submit()"` auto-submit** is the default filter pattern. | `board.html:18,29`; `hotels.html:35,45`; `places.html:37,47,57,78`; `tips.html:35,45,55`. | Keyboard users arrowing a `<select>` navigate away mid-browse; no debounce. | P2 |
| C7 | **Filter "labels" are sibling `<span class="fl">`, not `<label for>`.** | every `.filter-bar .fg > .fl + select/input`. | SR announces nameless combobox/date input (WCAG 4.1.2). | **P1** (a11y) |
| C8 | **No loading/skeleton for server-fetched pages.** Weather/AQ await real upstreams; only the easy-to-miss progress bar signals in-flight. | `dashboard.py:722` `weather_page`, `:774` `air_quality_page` (`async`). | Slow upstream = frozen old page, no feedback. | P2 |


---

## 4. Per-surface findings & proposals

### 4.1 Flights — `board.html` · `search.html` · `flight_detail.html`

**Weaknesses**

- **[P1] Board filter controls unlabeled.** `board.html:16-30` uses sibling
  `<span class="fl">`, not `<label>` → SR hears a nameless combobox/date input
  (WCAG 4.1.2). *(= C7)*
- **[P2] Auto-submit traps the keyboard.** `board.html:18,29`
  `onchange="this.form.submit()"` — arrowing the airport/date select navigates away
  mid-browse. *(= C6)*
- **[P2] Clickable board rows lack role/name + create a double tab-stop.**
  `board.html:70` `<tr class="frow" tabindex="0" data-href=…>` *and* the flight-number
  `<a>` inside it (`:85`) — both tabbable, both go to the same detail. SR hears a
  nameless `tabindex` row; the `<a>` is the only named path.
- **[P2] Airline brand-color chips can fail AA.** `.airline` uses raw airline brand
  hex as a background with white text (`board.html:82`, `search.html:115`); some
  airline brand colors are light enough that white-on-brand drops below 4.5:1.
- **[P3] No sticky table header.** The FIDS table can be long; the coral-rule header
  scrolls away, losing column context — unlike a real departures board.
- **[P3] Board "Estimated" column empty when no estimate** (`board.html:72`) — a blank
  cell reads as missing data, not "on time".
- **[P3] Live clock is JS-only and never shows seconds/date** (`board.html:101-107`)
  — a FIDS board's whole identity is a ticking clock; a `HH:MM` minute clock undersells
  it.

**Proposals**

- **Wrap each `.fg` control in `<label>`** (visually the `.fl` span becomes the label
  text; keep the existing look). One-line-per-control change in every filter bar.
  *Alignment: fixes C7 without new chrome.*
- **Replace `onchange=submit` with a single "Apply"/"View" button + Enter-to-submit**,
  and keep the existing `.fb-btn` as the submitter (board already has one at
  `board.html:32`). *Alignment: removes C6 keyboard trap; button already on-system.*
- **Make the row a single keyboard target:** drop `tabindex` on `.frow`, keep the
  flight-number `<a>` as the tab stop, and make the *whole row* a click/Enter shortcut
  via event delegation that fires `a.click()` (not `location.href`). Add
  `aria-label="Flight {number} — {from} to {to}"` to the `<a>`. *Alignment: removes
  double tab-stop + names the action; stays FIDS-style.*
- **Airline chip: guarantee AA** by giving `.airline` a `min`-contrast treatment —
  pick dark-on-light vs light-on-dark per chip luminance (a tiny inline
  `style="--ink"` already used on visa stamps is the precedent), or always render the
  code in `--on-accent` over a darkened brand chip. *Alignment: extends the
  "lighten colored text on same-hue tints toward Ink for AA" DESIGN.md Do.*
- **Sticky `<thead>`** for `table.fids` (`position: sticky; top: 0; z-index: var(--z-sticky)`).
  *Alignment: reinforces the FIDS metaphor; uses the existing z-scale.*
- **Empty "Estimated" → render an "on time" micro-pill** (reuse the green `.remark`
  pattern) when `estimated` is null. *Alignment: reuses status-pill vocabulary.*


### 4.2 Discovery — `hotels.html` · `places.html` · `tips.html` · `visa.html` · `_explore.html`

**Weaknesses**

- **[P1] Modals don't manage focus** (hotels `.hm-dialog`, places modal) — no trap,
  no initial focus, no restore, no `inert` behind. *(= C3)*
- **[P2] Hotel/place "card as button" duplicates the tab path.** `hotels.html:80`
  `<article role="button" tabindex="0">` and `places.html` `.place-card` — the whole
  card is a button *and* contains interactive children (save button `places.html:565`,
  image). Nested interactives inside `role="button"` are an ARIA anti-pattern and the
  save `＋` button must `stopPropagation` to survive (`places.html:566`).
- **[P2] Hotel modal photo has no loading/error state** — `hm-image` `.src` is set
  from `data-image` (`hotels.html:354`); a broken/placeholder image shows the raw
  `--photo-bg` backdrop with alt text only.
- **[P2] Places city autocomplete is hand-rolled** (`places.html:23-33` +
  `#city-dropdown`) with no `role="combobox"`/`role="listbox"`/`aria-activedescendant`
  — keyboard arrow navigation through suggestions isn't exposed to SR, and it diverges
  from every other page's native `<select>` city filter.
- **[P2] Tips two-column layout can orphan a category** at the column break
  (`tips.html:349-359` `break-inside: avoid` is set, but the sticky jump-nav
  `.guide-jump` doesn't highlight the in-view category).
- **[P3] `_explore` cross-link strip is appended inconsistently** — weather/aq/hotels
  import it but not all call `explore()`; tips/visa call it; places does not. The
  "Explore {city}" mental model is incomplete across surfaces.
- **[P3] Visa picker "Visa required" tiles** (`visa.html:54` `.page.is-req`) use
  `--red` — correct, but the stamp verdict is color-only on the tile face until you
  open the record (the number/"Visa required" text is there, so this is AA-fine; noted
  only as a confirmation, not a defect).
- **[P3] Hotel sort has no "distance to center"** despite places having geo data —
  a missed scannability lever for "where to stay".

**Proposals**

- **Shared modal focus utility** (see §5 P1-1) applied to hotels/places/bookings/agent.
  *Alignment: one mechanism, on-system, fixes C3 everywhere.*
- **De-nest the card button.** Make the `.hotel-card`/`.place-card` a single
  `<a href>` (or `role="button"` with `aria-haspopup="dialog"`) and lift the save `＋`
  *out* of it as a sibling absolutely-positioned button, so `stopPropagation` hacks go
  away. *Alignment: removes ARIA anti-pattern; keeps the same visual.*
- **Hotel image fallback:** add `onerror` → swap to a tokenized placeholder
  (emoji + `--photo-bg`) and an `aria-label`; show a subtle skeleton while loading.
  *Alignment: extends the `.photo-bg` backdrop primitive.*
- **Places city filter → reuse the native `<select>`** used by every other surface
  (hotels/tips/visa/weather/aq) for consistency, OR promote the autocomplete to a
  proper combobox pattern with `role/aria-*`. *Alignment: consistency + a11y.*
- **Tips jump-nav scroll-spy:** highlight the current `.guide-jump` link via
  `IntersectionObserver` on each `.cat` section. *Alignment: pure enhancement to the
  existing sticky nav; reduced-motion-safe.*
- **Standardize `_explore`** on every city-scoped page (add to places; ensure weather/
  aq/hotels/tips/visa all render it with the right `current=`). *Alignment: one
  cross-navigation pattern, already on-system.*
- **Hotel "walk to center" badge** derived from place geo/haversine (`core/geo`), as a
  `.chip`. *Alignment: reuses existing geo util; extends amenity-chip vocabulary.*


### 4.3 Live lookup + ledger — `weather.html` · `air_quality.html` · `bookings.html`

**Weaknesses**

- **[P1] Cancel booking fires with no confirmation** — `bookings.html:268-278` POSTs
  `/bookings/{id}/cancel` then `location.reload()` on a single click; `tpConfirm`
  (`base.html:889`) exists but is unused. Misclick/stray Enter = irreversible cancel.
- **[P1] Booking modal opens without moving focus; no trap/restore.** *(= C3)*
- **[P2] No loading/error UI for live upstreams.** Weather/AQ are `async` server calls
  (`dashboard.py:722/774`); on a slow/failed Open-Meteo response the user sees the
  prior page frozen with only the thin progress bar. The error path renders a plain
  `.error` line (`weather.html:74-75`) with no retry affordance.
- **[P2] "No city selected" initial state is a bare filter bar** — weather/AQ landing
  shows just the city `<select>` + button; no hero/illustration explaining what you'll
  get (contrast with the rich home page). The empty state only appears *after* a
  failed lookup.
- **[P2] Ledger row → modal loses the row's context.** `bookings.html:80` `.brow`
  `tabindex="0"` + click opens a modal, but the row has no `aria-label`/`role`; the
  confirmation code `<code>` is the only named thing. Same double-tab issue as the
  FIDS row.
- **[P3] No refresh/staleness** on weather/AQ — no "updated 2m ago" or refresh button.
  *(= C9)*
- **[P3] AQI 6-band ramp** is AA-safe (label+number redundant), but the dial value
  `rgb(var(--cglow))` text on the gradient can be low-contrast at the "Good" green end
  on some monitors — worth a quick AA spot-check.
- **[P3] Bookings "Create via POST /flights/book" hint** (`bookings.html:53`) is
  dev-only prose in an empty state — fine for the audience, but a one-click
  "try a sample booking" would be friendlier.

**Proposals**

- **Confirm cancel with `tpConfirm`** (the existing themed dialog) before the POST;
  on confirm, disable the button → "Cancelling…" → reload (current behavior preserved).
  *Alignment: uses the on-system dialog; removes the data-safety P1; no new chrome.*
- **Apply the shared modal focus utility** to the booking modal; on open focus the
  close/copy button, on close restore to the row. *(= C3 fix.)*
- **Loading skeleton for weather/AQ:** render a tokenized `.card` skeleton in the
  panel area while the async handler resolves (server can stream a partial, or add a
  tiny inline "Fetching live data…" state). Add a **retry** link to the `.error` block.
  *Alignment: extends `.card` + `.empty` vocabulary; respects reduced-motion.*
- **Initial-state hero for weather/AQ** (no city yet): a small illustrated panel
  ("Pick a city to see a live forecast") reusing the `.empty` pattern but elevated to a
  first-paint state. *Alignment: reuses `.empty`/`.empty-ico`; no new component.*
- **Ledger row → single `<a>`/button target** mirroring the FIDS-row fix (§4.1); give
  the row an `aria-label` summarizing type + code + customer. *Alignment: consistency
  with the board fix.*
- **"Updated {time} · Refresh"** chip on weather/AQ (server can pass a `fetched_at`;
  Refresh = same-URL GET). *Alignment: small `.page-meta` extension; honesty about
  mock/live staleness (PRODUCT.md "credible realism").*
- **AA spot-check the AQI dial** value contrast at each band; if "Good" fails, render
  the number in `--ink` with a colored ring instead of colored text. *Alignment:
  honors the DESIGN.md "lighten colored text on same-hue tints toward Ink for AA" Do.*


### 4.4 Ops / config — `agent_config.html` · `agent_config_edit.html` · `prompt_detail.html` · `prompt_diff.html` · `_prompt_sidebar.html`

**Weaknesses**

- **[P1] Native `confirm()` on the standalone edit form** vs styled confirm in the
  modal — `agent_config_edit.html:30` `onsubmit="return confirm(...)"` vs
  `agent_config.html` bespoke `#confirm-modal` (`:439-461`). Violates the repo's
  no-native-dialog rule and the two surfaces feel different for one action.
- **[P2] Dual edit paths, no canonical owner.** The modal (`agent_config.html:90+`)
  and the standalone page (`agent_config_edit.html`) both edit the same config; the
  nav/`⌘K` only links the list. It's unclear which is primary, and they diverge (modal
  has model-chip suggestions + styled confirm; page has a `<datalist>` + native
  confirm).
- **[P2] Agent-config modal focus** — `agent_config.html:390` focuses `#am-provider`
  on open (good!) but has no trap/restore and stacks a confirm dialog without
  managing focus between the two. *(= C3 partial)*
- **[P2] Prompts workspace has no copy/raw-download** of a version — a dev reading a
  prompt can't grab it as a file to diff locally. The compare bar
  (`prompt_detail.html:18-37`) defaults to "previous → latest" which is sensible.
- **[P2] Diff view: no keyboard line nav / "jump to next change."** Long prompts
  scroll a lot; `prompt_diff.html` unified/side-by-side toggle is good but there's no
  "next hunk" shortcut or change-count summary.
- **[P3] `prompt_detail` content is a raw `<pre>`** with no line numbers / no
  word-wrap toggle — fine, but a "wrap / no-wrap" toggle + line numbers would help
  long prompts.
- **[P3] Sidebar (`_prompt_sidebar.html`) is sticky but not scroll-spy** — selecting a
  prompt doesn't keep the active item in view when the list is long.

**Proposals**

- **Delete the native `confirm()`** in `agent_config_edit.html` and route the submit
  through `tpConfirm` (or, better, **deprecate the standalone page** in favor of the
  modal — see next). *Alignment: one confirmation mechanism, on-system.*
- **Pick the modal as canonical** edit surface; either remove the standalone route or
  redirect `/dashboard/agent-config/{name}` GET to the list with the modal pre-opened
  (via a query param + `?agent=`). *Alignment: removes the dual-path confusion; fewer
  templates to maintain.*
- **Apply the shared modal focus utility** to the agent modal, and when the confirm
  dialog stacks, move focus to `cmConfirm` and back to the modal on cancel (the code
  already partially handles Esc-stacking at `agent_config.html:407-411`).
- **Prompts: "Copy" + "Download .txt"** buttons on `prompt_detail` content card
  (`:51`), reusing the bookings copy-button pattern (`bookings.html:259-265`).
  *Alignment: reuses an existing on-system micro-interaction.*
- **Diff: "next/prev change"** via a small JS that jumps between `.diff-add`/`.diff-del`
  rows, + a change-count badge ("12 changes"). *Alignment: extends the diff-toggle
  group; keyboard-only; reduced-motion-safe.*
- **Prompt content: line numbers + wrap toggle** (a `.prompt-content` opt-in class).
  *Alignment: extends the mono content primitive; no new component.*
- **Sidebar scroll-spy / active-scroll-into-view** on selection. *Alignment: small JS,
  on-system.*

### 4.5 Home — `index.html`

The landing page is the one welcome surface and is *intentionally* livelier; it's in
good shape (sunset sky, route-arc plane, itinerary timeline with per-stop hues). Only
minor notes:

- **[P3] The itinerary "stops" duplicate the topbar tabs** — fine as a narrative, but
  the stops could surface a live count per section (e.g. "Flights · 24 today") to
  reward the click and tie the welcome to the data.
- **[P3] The animated route plane + journey fill** are lovely but the
  `prefers-reduced-motion` static end-state (`index.html:276-282`) hard-codes
  `width:80%`/`left:90%` — verify that reads as "arrived" rather than "stuck".
- No a11y defects found here beyond the cross-cutting C1/C2/C4.


---

## 5. Prioritized roadmap (consolidated proposals)

Grouped by severity, then leverage. Each item names file(s) and stays within Jinja2 +
vanilla JS + the Sunset tokens. **Wave 1 = P1, ship first.**

### Wave 1 — P1 (a11y + data-safety hardening)

- **P1-1 · Shared modal focus utility (fixes C3).** One tiny vanilla-JS helper in
  `base.html` (`window.openDialog(modal, {trigger, initialFocus})`): store
  `activeElement`, set `inert`/`aria-hidden` on siblings, focus `initialFocus`, install
  a Tab trap + Esc-close, restore focus on close. Refactor hotels/places/bookings/agent
  open/close to call it. *Files: `base.html`, `hotels.html`, `places.html`,
  `bookings.html`, `agent_config.html`.*
- **P1-2 · Confirm destructive cancel.** Wrap `bookings.html:268-278` in `tpConfirm`
  before the POST. *File: `bookings.html`.*
- **P1-3 · Label every filter control (fixes C7).** Convert `.fg > .fl + control` to
  `<label>` across all filter bars (mechanical, one template each). *Files: `board.html`,
  `hotels.html`, `places.html`, `tips.html`, `visa.html`, `weather.html`,
  `air_quality.html`, `bookings.html`.*
- **P1-4 · Remove native `confirm()` + collapse dual edit path.** Route
  `agent_config_edit.html` submit through `tpConfirm`; pick the modal as canonical
  (redirect the page GET to the list w/ `?agent=`). *Files: `agent_config_edit.html`,
  `agent_config.html`, `dashboard.py:915`.*

### Wave 2 — P2 (friction / consistency / state-completeness)

- **P2-1 · Stop `onchange` auto-submit trapping the keyboard (C6).** Make `.fb-btn`
  the explicit submitter everywhere. *All filter bars.*
- **P2-2 · Consistent `:focus-visible` ring (C4).** Shared rule in `base.html`:
  `:where(.tab,.fb-link,.explore a,.seg a,.version-pill,.toggle-chip,.back):focus-visible
  { box-shadow: var(--ring); }`. *File: `base.html`.*
- **P2-3 · `color-scheme: dark` on the shell (C2).** One line in `base.html` `:root`.
  *File: `base.html`.*
- **P2-4 · Skip-link (C1).** `<a class="skip" href="#main">` first in body + `id="main"`
  on `.wrap`; hidden until focused. *File: `base.html`.*
- **P2-5 · Loading skeleton + retry for weather/AQ (C8).** Tokenized skeleton while
  the async handler resolves + retry link on `.error`. *Files: `weather.html`,
  `air_quality.html`, `dashboard.py:722/774`.*
- **P2-6 · De-nest card-as-button (hotels/places) + single row target (board/ledger).**
  Lift save `＋` out of the card; make clickable rows a single `<a>`/button w/
  `aria-label`. *Files: `hotels.html`, `places.html`, `board.html`, `bookings.html`.*
- **P2-7 · Standardize `_explore`** on every city-scoped page. *File: `places.html`
  (add); verify others.*
- **P2-8 · Places city filter consistency** (native `<select>` or proper combobox
  ARIA). *File: `places.html`.*
- **P2-9 · Prompts copy/download + diff "next change" + change-count.** *Files:
  `prompt_detail.html`, `prompt_diff.html`.*

### Wave 3 — P3 (polish / density / delight)

- **P3-1 · Sticky FIDS `<thead>`** (`position: sticky; top: 0`).
- **P3-2 · "On time" micro-pill** for empty Estimated; richer live clock (seconds +
  date) on the board.
- **P3-3 · "Updated {time} · Refresh"** on weather/AQ.
- **P3-4 · AA spot-check AQI dial** value contrast per band.
- **P3-5 · Hotel "walk to center" chip** from `core/geo` haversine; distance sort.
- **P3-6 · Tips jump-nav scroll-spy** + prompt-sidebar active-scroll-into-view.
- **P3-7 · Group the topbar** (Plan / Live / Ops) with a subtle divider — only if C5
  still feels flat after Wave 1–2.
- **P3-8 · Home itinerary stops show a live count** per section.


---

## 6. Accessibility summary (vs WCAG AA — the PRODUCT.md target)

- **Fail / must-fix:** 4.1.2 (unlabeled filter controls — C7/P1-3); 2.1.2/2.4.3/2.4.7
  (modal focus mgmt — C3/P1-1); 2.4.7 (focus-restore on cancel-confirm stacking).
- **Likely fail / verify:** `--muted` (`#a89c96`) on `--panel` (`#221d1a`) is the
  PRODUCT.md-flagged risk — spot-check `.page-meta`/`.sub`/`.empty-hint` and the
  airline-chip white-on-brand case. The AQI "Good" green dial text wants a check.
- **Easy wins:** skip-link (C1), `color-scheme` (C2), consistent `:focus-visible`
  (C4), de-nesting card-buttons (P2-6). All low-risk, high-payback.
- **Already good:** color-not-alone discipline (status/topic always labeled),
  `prefers-reduced-motion` global + per-surface, keyboard paths exist, `aria-hidden`
  toggling on modals (just missing the focus half).

---

## 7. Open questions / decisions needed

1. **Agent-config: modal vs standalone page?** Pick the canonical edit surface
   (recommend modal) so we can delete one template + the native `confirm()`.
2. **Auto-submit policy:** remove `onchange=submit` everywhere (recommended), or keep
   it only for one-tap toggles (the `Recommended`/`Essential only` `.toggle-chip`)?
3. **Weather/AQ loading state:** server-stream a skeleton partial, or accept the
   progress-bar-only signal?
4. **Hotel distance-to-center:** is place geo available at hotel-render time in
   `dashboard.py:298` `hotels_page`, or does it need a new service call?
5. **Topbar grouping (C5):** worth the visual change given ⌘K already covers fast
   traversal?
6. **Live clock:** seconds + date (more "FIDS"), or stay minimal to avoid noise?

---

## 8. Suggested next step

Promote **Wave 1 (P1-1 … P1-4)** into `specs/dashboard-ui-ux-enhancement/PLAN.md` as
the first implementation slice — surgical, high-leverage, and they unblock the WCAG-AA
gaps. Wave 2/3 follow as separate slices. Verify each with `make dev` + a keyboard-only
pass + a reduced-motion pass, per the repo's "evidence over assertion" rule
(`AGENTS.md`).
| C9 | **No staleness/refresh affordance** on live data. | `weather.html:260`, `air_quality.html:295`. | Can't tell if a reading is fresh or a cached prior GET. | P3 |
| C10 | **Three confirmation mechanisms.** `tpConfirm` (`base.html:889`) unused by cancel; `agent_config.html` uses bespoke `#confirm-modal`; `agent_config_edit.html` uses native `confirm()`. | — | Inconsistent + one violates the no-native-dialog rule. | P2 |