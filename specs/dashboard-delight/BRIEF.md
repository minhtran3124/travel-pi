# Design Brief — Dashboard Delight (slice 2 of the dashboard UI/UX enhancement)

> Produced by `/impeccable shape`. Register: **product** (`apps/api/PRODUCT.md`).
> Design system: **"Sunset Departures Board"** (`apps/api/DESIGN.md`). Deep-research
> evidence: template survey + live screenshots of all `/dashboard/*` pages, 2026-07-11.

## 1. Feature Summary

Amplify the visually flat pages of the API dashboard — flights board, bookings,
search, agent-config — with **travel-metaphor set pieces** that take the FIDS/airport
world literally, plus motion-hygiene fixes. One hero moment (the split-flap flights
board); everything else is supporting cast. Strong pages (home hero, boarding pass,
hotels, tips/visa pickers, weather, air quality) are explicitly untouched.

## 2. Primary User Action

Unchanged: *"Did the endpoint return what I expected, and does it look right?"* —
answered in seconds. Every set piece must make scanning **faster or more credible**
(the mock reads as a real airport product), never slower. Delight that costs clarity
is cut.

## 3. Design Direction

- **Color strategy:** Restrained (project default). No new hues — coral stays the
  only brand voice; status/topic palettes stay closed. The theatrics are carried by
  **motion and structure**, not color.
- **Scene sentence:** A developer glances at a second monitor in a dim room mid-task;
  the dashboard should feel like the airport departures hall he's simulating —
  alive, ticking, trustworthy — without ever demanding attention. (Dark theme,
  already committed.)
- **Anchor references:** a real split-flap Solari departures board (the settle
  clatter, not a carousel); a paper airline ticket stub (perforation, stamp);
  the existing boarding-pass page in this same dashboard (`flight_detail.html`) —
  the theatrics extend *its* language, they don't invent a new one.

## 4. Scope

- **Fidelity:** production-ready, server-rendered Jinja2 + vanilla CSS/JS only
  (no libraries — constraint confirmed in research).
- **Breadth:** 4 flat pages + 2 hygiene fixes + 1 stretch page.
- **Interactivity:** shipped-quality; every animation honors `prefers-reduced-motion`.
- **Time intent:** plan now (`PLAN.md`), execute in a later session via
  `/executing-plans`.

## 5. Layout Strategy

No page changes its information architecture. The amplification is **surface-level
theatrics on existing structure**:

- **/flights (HERO) — the split-flap settle.** On load, the remarks/estimated cells
  settle with a brief split-flap flip (CSS 3D `rotateX` two-frame flip), staggered
  ~30ms per row, total ≤600ms, **once per navigation**. The clock gains the FIDS
  colon-blink. A thin board dateline ("SAT 11 JUL · SGN · ARRIVALS") sits above the
  table head in existing label style. This is the one orchestrated entrance the
  product register allows — the hero moment, spent here deliberately.
- **/bookings — the ticket-stub ledger.** Each row reads as a ticket stub: a
  perforated left edge on the confirmation cell (dashed hairline + notch), mono
  stub code, and a **rotated red "CANCELLED" stamp** treatment (low-opacity,
  border + uppercase) replacing the plain cancelled pill. Table semantics stay —
  it's styling, not restructure.
- **/flights/search — the route-arc empty state.** Empty/no-result states reuse the
  home hero's dashed route-arc + plane motif as a small inline SVG (drawn once,
  static under reduced motion). Results settle like the board (shared pattern,
  page-scoped code).
- **/agent-config — the crew roster.** Remove the colored left-stripe section
  markers (**explicit design-system ban**, found in research). Role sections get
  the standard glyph + count-chip header; agent cards get role-hued icon tiles and
  the same-hue hover glow already proven on hotel cards; the supervisor card gets
  visual seniority (wider span / stronger border) as the "flight director".
- **Hygiene:** `tips.html` and `places.html` gain the missing
  `prefers-reduced-motion` guards.
- **Stretch — /visa passport stamp.** The visa verdict enters as a stamp-down
  (scale 1.15→1 + opacity, ~200ms, once; instant under reduced motion), styled as a
  passport stamp (rounded border, slight rotation, uppercase, status-colored within
  the existing spectrum).

## 6. Key States

- **Board settle:** plays once per full navigation; view-transition back/forward must
  not replay it into jank; reduced-motion = rows render final state instantly.
- **Cancelled stub:** stamp must keep the text label (no color-alone meaning) and AA
  contrast; confirmed rows stay calm — the stamp is the exception, not the rhythm.
- **Empty search:** arc + friendly one-liner + hint (existing `.empty` grammar).
- **Agent-config unset values:** unchanged (— placeholders); roster styling must not
  imply "custom" where config is default.
- **Both themes:** every set piece verified in Sunset *and* Nightfall.

## 7. Interaction Model

No new interactions — hover/click/keyboard behavior is untouched (slice 1 just
hardened it; do not regress focus management, `openDialog`, or filter Apply
buttons). Motion is feedback, not navigation: settle on load, stamp on render,
glow on hover. All animation is CSS-only; JS only for the one-shot settle trigger
and the existing clock.

## 8. Content Requirements

- Board dateline: `{DAY DD MON} · {IATA} · {ARRIVALS|DEPARTURES}` from existing
  template context.
- Cancelled stamp: the word `CANCELLED` (existing i18n-free dashboard English).
- Empty-search copy: keep current friendly voice ("No flights on this route yet —
  try another date"); no new marketing copy, no exclamation points.
- No images/assets required: motifs are inline SVG + CSS, consistent with the
  no-libraries constraint.

## 9. Recommended References (during implementation)

`animate.md` (settle/stamp timing, reduced-motion), `polish.md` (final pass),
the parent skill's absolute bans (side stripes already flagged; no glassmorphism,
no gradient text).

## 10. Open Questions

None — defaults asserted: hero = flights board; visa stamp is stretch (wave 3,
cuttable); prompts pages stay out of scope this slice.
