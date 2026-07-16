---
slug: dashboard-delight
status: executed
owner: minhtran
created: 2026-07-11
---

# Dashboard Delight — travel-metaphor theatrics for the flat pages

Slice 2 of the BE dashboard UI/UX enhancement (slice 1 = a11y/data-safety hardening,
PR #86). Design direction and evidence: `specs/dashboard-delight/BRIEF.md`.

## 1. Motivation

The dashboard's strong pages (home hero, boarding pass, hotels, pickers, AQI) carry
the "Sunset Departures Board" identity; the flat pages (flights board, bookings,
search, agent-config) read as plain tables/grids and drag the whole surface toward
"generic admin". Research (template survey + live screenshots, 2026-07-11) also found
two design-system violations to fix: colored left-stripe section markers in
`agent_config.html` (banned) and missing `prefers-reduced-motion` guards in
`tips.html` / `places.html`.

## 2. Non-goals

- No changes to routers, services, or any Python — **templates only**.
- No redesign of already-strong pages (index, flight_detail, hotels, places, tips
  content, weather, air-quality) beyond the named hygiene fixes.
- No new colors, no JS libraries, no chart library, no prompts-page work.
- No IA/interaction changes — slice 1's focus management and filter behavior must
  not regress.

## 3. Success Criteria

1. Full dashboard test selection stays green (same selection as slice 1: 299 passed).
2. Zero design-system ban violations in changed templates (no `border-left/right`
   accent stripes > 1px, no gradient text, no glassmorphism).
3. Every new animation has a `prefers-reduced-motion` alternative; board settle plays
   once per navigation and total ≤600ms.
4. Both themes (Sunset / Nightfall) verified by screenshot for every changed page.
5. AA holds: stamp/stub/roster text ≥4.5:1 on its surface; no color-alone meaning.

## 4. Tasks

### Task 1.1 — Motion hygiene: tips + places reduced-motion guards

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/templates/tips.html, apps/api/app/templates/places.html</files>
  <action>Add @media (prefers-reduced-motion: reduce) guards covering every keyframe/transition defined in these two templates (research found zero guards; places.html defines a keyframe). Instant/no-motion fallback, matching the pattern already used in base.html.</action>
  <verify>cd apps/api && grep -q "prefers-reduced-motion" app/templates/tips.html && grep -q "prefers-reduced-motion" app/templates/places.html && ../../.venv/bin/python -m pytest tests/api -k "tips or places" -q</verify>
  <done>Both templates define reduced-motion fallbacks for all their animations; tests pass.</done>
</task>
```

### Task 1.2 — Agent Config as crew roster (+ ban fix)

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/templates/agent_config.html</files>
  <action>Remove the colored left-stripe section markers (design-system ban) and replace with the standard glyph + count-chip section header used elsewhere. Give each agent card a role-hued icon tile (existing topic palette; no new hues) and the same-hue hover glow proven on hotel cards. Give the supervisor card visual seniority (wider span or stronger border) as the "flight director". Keep the modal edit flow and unset-value placeholders exactly as slice 1 left them.</action>
  <verify>cd apps/api && ! grep -E "border-left:[^;]*(2|3|4)px" app/templates/agent_config.html && ../../.venv/bin/python -m pytest tests/api -k "agent_config" -q</verify>
  <done>No accent side-stripes remain; roster reads role-grouped with supervisor emphasis; tests pass.</done>
</task>
```

### Task 2.1 — HERO: split-flap settle on the flights board

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/templates/board.html</files>
  <action>Add the one-shot split-flap settle: remarks + estimated cells flip in via CSS 3D rotateX two-frame flip, staggered ~30ms/row, total ≤600ms, triggered once per full navigation (guard against view-transition replay). Add FIDS colon-blink to the existing clock and a thin board dateline ("SAT 11 JUL · SGN · ARRIVALS") above the table head in existing label style from template context. All CSS/JS scoped to board.html. prefers-reduced-motion renders final state instantly (content never gated on animation).</action>
  <verify>cd apps/api && grep -q "prefers-reduced-motion" app/templates/board.html && ../../.venv/bin/python -m pytest tests/api -k "board or dashboard" -q</verify>
  <done>Board settles once like a Solari board, clock blinks, dateline present; reduced-motion instant; tests pass.</done>
</task>
```

### Task 2.2 — Bookings as ticket-stub ledger

```xml
<task id="2.2" wave="2">
  <files>apps/api/app/templates/bookings.html</files>
  <action>Style each booking row as a ticket stub while keeping table semantics: perforated edge on the confirmation cell (dashed hairline + notch, echoing flight_detail's perforation), mono stub code, and replace the plain cancelled pill with a rotated low-opacity red "CANCELLED" stamp (border + uppercase text — label kept, no color-alone meaning, AA on panel). Confirmed rows stay calm. Do not touch the tpConfirm cancel flow from slice 1.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api -k "bookings" -q</verify>
  <done>Ledger reads as stubs, cancelled bookings carry the stamp, a11y/flow unchanged; tests pass.</done>
</task>
```

### Task 2.3 — Search route-arc empty state + settle parity

```xml
<task id="2.3" wave="2">
  <files>apps/api/app/templates/search.html</files>
  <action>Upgrade empty/no-result states with a small inline dashed route-arc + plane SVG (motif from index.html hero, redrawn minimal; static under reduced motion) inside the existing .empty grammar, keeping current friendly copy. Give results the same settle treatment as board.html (pattern duplicated page-scoped; base.html untouched).</action>
  <verify>cd apps/api && grep -q "prefers-reduced-motion" app/templates/search.html && ../../.venv/bin/python -m pytest tests/api -k "search or flight" -q</verify>
  <done>Empty search shows the route-arc motif; results settle consistently; tests pass.</done>
</task>
```

### Task 3.1 — Stretch: visa passport stamp

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/templates/visa.html</files>
  <action>Render the visa verdict as a passport stamp: rounded border, slight rotation, uppercase, colored within the existing status spectrum; stamp-down entrance (scale 1.15→1 + opacity, ~200ms, once) with instant reduced-motion fallback. Cuttable if wave 2 review raises rework.</action>
  <verify>cd apps/api && grep -q "prefers-reduced-motion" app/templates/visa.html && ../../.venv/bin/python -m pytest tests/api -k "visa" -q</verify>
  <done>Verdict reads as a stamp in both themes; tests pass.</done>
</task>
```

### Task 4.1 — Full-suite + visual audit

```xml
<task id="4.1" wave="4">
  <files>specs/dashboard-delight/TEST_MATRIX.md, specs/dashboard-delight/SUMMARY.md</files>
  <action>Run the slice-1 dashboard test selection; screenshot every changed page in Sunset and Nightfall plus one reduced-motion pass; check bans (side-stripes, gradient text, glassmorphism) and AA on stamp/stub/roster text; record evidence rows in TEST_MATRIX.md and the Verify table in SUMMARY.md.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api -k "dashboard or places or tips or visa or bookings or hotels or board or agent_config" -q</verify>
  <done>Suite green; both-theme + reduced-motion screenshots recorded; no ban violations; evidence filed.</done>
</task>
```

## 5. Risks

- **Settle jank on view transitions** — the root `vt-in/vt-out` transition could
  replay or fight the flip; task 2.1 must gate the settle to full navigations.
- **Stamp legibility** — rotated low-opacity red on dark panel risks AA; verify
  contrast at implementation, lighten toward ink per the Readable-on-Tint rule.
- **Scope creep into strong pages** — the motif extraction from index.html (2.3)
  must not modify index.html.
- **Shared-file temptation** — settle CSS belongs page-scoped (board, search);
  putting it in base.html would create wave overlap and regression surface.

## 6. Status Log

- 2026-07-11 — Plan proposed (research + brief complete; awaiting execution session).
- 2026-07-11 — Executed. All 6 implementation tasks (1.1, 1.2, 2.1, 2.2, 2.3, 3.1)
  complete; audit (4.1) recorded in TEST_MATRIX.md + SUMMARY.md. Full suite green
  (299 passed); bans clean; AA verified both themes; reduced-motion on all
  changed templates. Remaining: live cross-theme browser screenshot pass before
  merge.
