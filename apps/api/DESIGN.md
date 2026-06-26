---
name: Travel Planner Dashboard
description: A dark, warm-coral, friendly operations board for the mock Travel Planner API
colors:
  coral-bright: "#ff6f5e"
  coral-deep: "#c2410c"
  coral-soft: "#ffa99c"
  on-coral: "#3a0f08"
  void: "#1a1614"
  panel: "#221d1a"
  panel-raised: "#2e2723"
  line: "#3e342e"
  line-soft: "#2f2823"
  ink: "#efe9e6"
  muted: "#a89c96"
  amber: "#fbbf24"
  green: "#34d399"
  orange: "#fb923c"
  cyan: "#38bdf8"
  red: "#f87171"
  hotel-blue: "#2563eb"
typography:
  display:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "2.4rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.35rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.1rem"
    fontWeight: 800
    lineHeight: 1.3
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.68rem"
    fontWeight: 700
    letterSpacing: "0.08em"
  mono:
    fontFamily: "Menlo, Consolas, SF Mono, monospace"
    fontSize: "0.8rem"
    fontWeight: 400
rounded:
  sm: "8px"
  md: "12px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.coral-deep}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "0 18px"
    height: "34px"
  input:
    backgroundColor: "{colors.panel-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 10px"
    height: "34px"
  card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "16px"
  remark-pill:
    backgroundColor: "rgba(56,189,248,0.14)"
    textColor: "{colors.cyan}"
    rounded: "{rounded.pill}"
    padding: "3px 11px"
  status-pill:
    backgroundColor: "rgba(52,211,153,0.13)"
    textColor: "{colors.green}"
    rounded: "{rounded.pill}"
    padding: "3px 11px"
---

# Design System: Travel Planner Dashboard

## 1. Overview

**Creative North Star: "Sunset Departures Board"**

A dark airport flight-information board, evolved into a friendly, color-coded
operations dashboard for the mock Travel Planner API. The room is dark and
slightly warm-tinted; surfaces are low-glow cards lifted by soft shadows over a
deep warm-neutral canvas. A single coral is the system's voice — focus, action,
active state — while a fixed status spectrum and a per-topic color palette make
dense travel data (flights, hotels, places, tips, weather, bookings) instantly
scannable and warm rather than clinical.

The system is data-first but deliberately friendly: real emoji icons label
categories and amenities, content is color-coded by topic (each tips category
and hotel type carries its own hue), and interactive rows/cards/tiles respond
with a tinted hover in their own color. Numbers a user compares — times, prices,
durations, ratings, IDs — are always tabular figures.

It rejects: cream/AI-slop backgrounds and per-section uppercase eyebrows;
uniform icon+heading+text card grids as a reflex; gradient text; decorative
glassmorphism; and colored side-stripe borders. Color is functional — it
encodes status, topic, or scarcity, never decoration for its own sake.

**Key Characteristics:**
- Dark warm-neutral surfaces (Void → Panel → Panel Raised) separated by hairlines + soft shadows
- One coral brand voice; a closed status spectrum; a 10-hue topic palette
- Friendly emoji iconography for categories, amenities, and empty states
- Color-coded, interactive rows/cards/tiles with same-hue hover feedback
- Tabular figures everywhere data is compared

## 2. Colors

A dark warm-neutral palette: one coral accent and four neutral surface tones,
plus a fixed status spectrum and a topic-coding palette.

### Primary
- **Coral Bright** (#ff6f5e): Focus rings, active tab underline, table-head rule,
  hairline accents, the boarding-pass plane. Bright coral takes **dark** text
  (`On Coral` #3a0f08) on solid fills — never white (white fails AA on it).
- **Coral Deep** (#c2410c): Solid fills under **white** text — primary buttons,
  active segmented control, flight type badge.
- **Coral Soft** (#ffa99c): Text-accent on dark — links, clock, city names,
  "API Docs", back links.

### Neutral
- **Void** (#1a1614): App canvas. **Panel** (#221d1a): cards, table, nav.
  **Panel Raised** (#2e2723): inputs, table head, tiles, insets.
- **Line** (#3e342e) / **Line Soft** (#2f2823): borders and row dividers.
- **Ink** (#efe9e6): primary text. **Muted** (#a89c96): secondary text (AA on
  every surface — verified ≥5.0:1).

### Status (closed, fixed-meaning spectrum)
- **Green** (#34d399) landed / direct / confirmed · **Amber** (#fbbf24)
  estimated / seats-limited · **Orange** (#fb923c) delayed / stops · **Cyan**
  (#38bdf8) boarding · **Red** (#f87171) error / cancelled / seats-almost-gone.
- **Hotel Blue** (#2563eb): tags hotel bookings apart from flights.

### Topic palette (for color-coding)
Tips categories and hotel types each get a signature hue, applied to icon
tiles, count chips, jump pills, markers, and same-hue hover tints:
transport=amber, money=green, safety=red, culture=purple (#c084fc),
food=orange, connectivity=cyan, health=rose (#fb7185), etiquette=teal (#2dd4bf),
best_time=lime (#a3e635), language=indigo (#818cf8). Hotels: Hotel=sky (#38bdf8),
Resort=amber, Villa Resort=rose (#fb7185), Boutique=purple (#c084fc).
These topic/type hues are deliberately diverse and independent of the coral
brand voice — teal here is just one topic hue, not the accent.

### Named Rules
**The One Voice Rule.** Coral is the only *brand* color — actions, focus, active
state. Topic and status hues are a separate, functional vocabulary.

**The Functional Color Rule.** Every non-coral hue means something specific
(status, topic, or scarcity) and is paired with text or an icon — never color
alone. The status spectrum is closed; don't invent or reuse hues.

**The Readable-on-Tint Rule.** Colored text on a same-hue tint is lightened
toward Ink (`color-mix(--c 55%, ink)`) so small count chips still clear AA.

## 3. Typography

**Font:** Inter (system-ui fallback). **Mono:** Menlo/Consolas for IDs.

**Character:** One family across weights 400–800; personality comes from weight
contrast and tabular figures, not font pairing.

### Hierarchy
- **Display** (800, ~2.4rem): boarding-pass route codes, big numbers.
- **Headline** (800, 1.35rem, -0.01em): page titles.
- **Title** (800, 1.1rem): board/section/card names.
- **Body** (400, 0.9rem, line-height 1.6): text and table cells; prose ≤74ch.
- **Label** (700, 0.62–0.72rem, +0.08em, UPPERCASE): control/column labels only.
- **Mono** (0.8rem): resource IDs.

### Named Rules
**The Tabular Figures Rule.** Any compared number uses `tabular-nums`.
**The Functional Caps Rule.** Uppercase tracking is for control/column labels
and a single dateline — never per-section eyebrows.

## 4. Elevation

Hybrid: hairline borders + tonal layering define structure at rest; soft
shadows appear on state (hover, float). Cards lift on hover; modals float over a
blurred scrim.

### Shadow Vocabulary
- **Resting** (`0 2px 12px rgba(0,0,0,.45)`): standalone cards.
- **Lifted** (`0 14px 32px -8px rgba(0,0,0,.6), 0 4px 10px -4px rgba(0,0,0,.4)`):
  hover state, paired with a small translate (+ a same-hue glow ring on hotels).
- **Focus ring** (`0 0 0 3px rgba(45,212,191,.30)`): every focusable control.
- **Accent glow** (`rgba(45,212,191,.16)`): hover wash for rows / active chips.

## 5. Components

### Buttons & controls
Coral-deep primary button (white text), ghost link (muted, hairline border →
coral on hover), 34px controls, keyboard-accessible toggle chip with a
visually-hidden checkbox and `:focus-within` ring.

### FIDS table (flights / search / bookings)
Panel table, raised header with a coral bottom rule. **Status remarks are
color-coded pills** (boarding/delayed/landed/estimated/departed). Rows are
clickable to detail (the flight-number link is the keyboard path) and wash coral
on hover. Airline codes are brand-colored chips. Bookings status pills color by
state (confirmed=green, cancelled=red).

### Cards & grids
Hotel cards color-coded by property type (type pill, score-tiered rating badge,
emoji amenities, same-hue hover glow). Place cards with category color chips,
recommended/price overlays, and a detail modal. Tips render as a destination
**picker** (flag tiles) → field-guide (essentials lead, sticky topic jump-nav,
two-column category sections, interactive bordered tip rows color-coded by
topic).

### Signature: the Boarding Pass (flight detail)
A ticket: airline-colored side rail + code chip, large route codes with a dashed
route line and a coral plane, a die-cut **perforation** (notched dashed divider),
stub cells (price, duration, stops, and **seat-scarcity colored** seats-left),
and a mono flight ID.

### Empty states
Friendly: emoji icon + bold headline + a one-line hint/action link
(`.empty-ico` / `.empty strong` / `.empty-hint`).

### Modals
Native-feeling dialogs over a blurred dark scrim, `pop` entrance (disabled under
reduced-motion), Esc/backdrop close.

## 6. Do's and Don'ts

### Do:
- **Do** keep Coral Bright/Deep for brand actions/focus only; use the topic and
  status palettes for everything color-coded.
- **Do** pair every status/topic color with text or an icon (FIDS pill pattern).
- **Do** set compared numbers in `tabular-nums`.
- **Do** lighten colored text on same-hue tints toward Ink to hold AA.
- **Do** keep the coral focus ring on every focusable control, and a
  `prefers-reduced-motion` alternative for every animation.

### Don't:
- **Don't** use cream/parchment backgrounds, gradient text, hero-metric
  templates, or reflexive identical icon+heading+text card grids.
- **Don't** put uppercase tracked eyebrows above every section.
- **Don't** use `border-left/right` > 1px as a colored accent stripe.
- **Don't** add decorative glassmorphism (the only blurs are over-photo chips
  and modal scrims).
- **Don't** introduce a new accent or status hue, or reuse a status hue for a
  different meaning.
