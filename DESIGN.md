---
name: Travel Planner Dashboard
description: A dark, indigo, airport-FIDS dashboard for the mock Travel Planner API
colors:
  signal-indigo: "#6366f1"
  indigo-deep: "#4f46e5"
  indigo-soft: "#a5b4fc"
  void: "#0c0d12"
  panel: "#13141b"
  panel-raised: "#1a1c25"
  line: "#252836"
  line-soft: "#1e2030"
  ink: "#eef0f6"
  muted: "#7c829a"
  signal-green: "#34d399"
  caution-yellow: "#fbbf24"
  delay-orange: "#fb923c"
  boarding-cyan: "#38bdf8"
  alert-red: "#f87171"
  hotel-blue: "#2563eb"
typography:
  display:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.01em"
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
    letterSpacing: "normal"
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.68rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.08em"
  mono:
    fontFamily: "Menlo, Consolas, SF Mono, monospace"
    fontSize: "0.85rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
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
    backgroundColor: "{colors.signal-indigo}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "0 18px"
    height: "34px"
  button-primary-hover:
    backgroundColor: "{colors.indigo-deep}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
  button-ghost:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.muted}"
    rounded: "{rounded.sm}"
    padding: "0 13px"
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
    padding: "22px"
  chip:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "2px 9px"
  status-pill:
    backgroundColor: "rgba(52,211,153,0.12)"
    textColor: "{colors.signal-green}"
    rounded: "{rounded.pill}"
    padding: "3px 11px"
---

# Design System: Travel Planner Dashboard

## 1. Overview

**Creative North Star: "The Night Departures Board"**

This is an airport flight-information display reimagined as a polished SaaS
dashboard. The room is dark, the panels glow faintly, and every row of data is
lit so it can be read across the terminal at a glance. It exists to show a
developer what the mock Travel Planner API returned — flights, hotels, places,
tips, weather, bookings — and to make that data feel like a *real* travel
product, not a debugging dump. The mood is quiet trust: the interface recedes,
the numbers lead.

The system is data-first and dense, but warmer and more approachable than a raw
ops terminal. Corners are gently rounded (8–12px), transitions are short and
soft (0.15s), and a single indigo carries every action and active state.
Numbers — times, prices, durations, references — are set in tabular figures so
columns lock into a readable grid. Color is functional, never decorative:
indigo means "you can act here," and a small fixed vocabulary of status hues
(green/yellow/orange/cyan/red) means exactly one thing each.

What this system explicitly rejects: cream/sand backgrounds and uppercase
tracked eyebrows on every section (generic AI-SaaS slop); boxy gray
Bootstrap/AdminLTE panels and colored side-stripe alert borders (heavy
enterprise admin); and glassmorphism or decorative gradients bolted on at the
expense of legibility (over-designed marketing). Effects earn their place by
helping read the data or they are cut.

**Key Characteristics:**
- Dark, low-glow surfaces with hairline borders, not shadows, doing the
  separating
- One signature indigo accent; everything else is neutral or status color
- Tabular numerics everywhere data is compared
- A learnable status-color vocabulary carried alongside text, never color alone
- Soft, approachable geometry over hard utilitarian edges

## 2. Colors

A near-black indigo-tinted palette: a single vivid accent over four neutral
surface tones, plus a fixed status spectrum borrowed from real flight boards.

### Primary
- **Signal Indigo** (#6366f1): The system's one voice. Primary buttons, the
  active-tab underline, focus rings, row-hover wash, and the nav progress bar.
  It marks where a user can act or what is currently selected — nothing else.
- **Indigo Deep** (#4f46e5): The pressed/hover partner for Signal Indigo on
  solid fills.
- **Indigo Soft** (#a5b4fc): Links, clock readouts, "estimated" times, and
  inline accents on dark surfaces where full indigo would glare.

### Neutral
- **Void** (#0c0d12): The page background — the dark room the board hangs in.
- **Panel** (#13141b): Default surface for tables, cards, and the top nav.
- **Panel Raised** (#1a1c25): The next tier up — inputs, table headers, board
  strips, inner detail tiles.
- **Line** (#252836) / **Line Soft** (#1e2030): Hairline borders and row
  dividers. Borders, not shadows, do the structural work here.
- **Ink** (#eef0f6): Primary text. **Muted** (#7c829a): secondary text, labels,
  and inactive controls — verify it clears 4.5:1 on whatever panel it sits over.

### Status (a fixed vocabulary — each hue means one thing)
- **Signal Green** (#34d399): On-the-ground good — landed, direct, confirmed
  bookings.
- **Caution Yellow** (#fbbf24): Estimated / revised times.
- **Delay Orange** (#fb923c): Delayed, or "has stops."
- **Boarding Cyan** (#38bdf8): Boarding / in-progress.
- **Alert Red** (#f87171): Errors and failures.
- **Hotel Blue** (#2563eb): Reserved to tag hotel bookings apart from flights
  in the ledger.

### Named Rules
**The One Voice Rule.** Signal Indigo is the only brand color, and it appears on
a small fraction of any screen — actions, focus, active state. Its rarity is
what makes "you can act here" instantly legible. Never spend it on decoration.

**The Fixed Status Vocabulary Rule.** The six status hues are a closed set with
fixed meanings. Don't introduce a new status color, and don't reuse an existing
one for a different meaning. A reader should learn the board once.

## 3. Typography

**Display / Body Font:** Inter (with system-ui, -apple-system, Segoe UI, Roboto
fallbacks)
**Mono Font:** Menlo / Consolas / SF Mono — for machine identifiers only

**Character:** One family, worked across weights 400–800. The personality comes
from weight contrast and tabular figures, not from pairing two faces. Heavy
weights (800) anchor titles and key numbers; tracked small caps label every
control.

### Hierarchy
- **Display** (800, 1.6rem, line-height 1): Big route codes and the live clock.
  Always tabular numerics.
- **Headline** (800, 1.35rem, letter-spacing -0.01em): Page titles.
- **Title** (800, 1.1rem): Board titles, hotel/place names, card headings.
- **Body** (400–500, 0.875–0.9rem, line-height 1.5): Default text and table
  cells. Keep prose blocks to 65–75ch.
- **Label** (700, 0.62–0.72rem, letter-spacing 0.06–0.09em, UPPERCASE): Filter
  labels and table headers. The one place uppercase tracking is sanctioned —
  functional column/field labels, never decorative section eyebrows.
- **Mono** (0.85rem): Resource IDs (UUIDs, IATA codes) only.

### Named Rules
**The Tabular Figures Rule.** Any number a user compares down a column — time,
price, duration, reference — is set with `font-variant-numeric: tabular-nums`.
Always.

**The Functional Caps Rule.** Uppercase tracked text is allowed only on
control/column labels. It is forbidden as a per-section "eyebrow" above
headings.

## 4. Elevation

Flat by default. Depth comes from tonal layering — Void → Panel → Panel Raised
— and hairline borders, not from drop shadows. Shadows appear only as a
*response to state*: a card lifts on hover, a dialog floats above the page.
Borders define structure at rest; light handles interaction.

### Shadow Vocabulary
- **Resting card** (`box-shadow: 0 2px 12px rgba(0,0,0,.4)`): A subtle seat for
  standalone cards and search forms on the Void background.
- **Lifted** (`box-shadow: 0 8px 28px rgba(0,0,0,.55)`): The hover state for
  interactive cards (hotel grid), paired with a -3px translate.
- **Focus ring** (`box-shadow: 0 0 0 3px rgba(99,102,241,.25)`): The indigo
  ring on every focused input/select. Non-negotiable for accessibility.
- **Accent glow** (`rgba(99,102,241,.18)`): A translucent indigo wash for
  hovered table rows and active toggle chips — light, not shadow.

### Named Rules
**The Borders-Not-Shadows Rule.** Surfaces are separated by 1px lines at rest.
Reach for a shadow only when an element changes state (hover, focus, float).

## 5. Components

Components should feel **soft and approachable** — gently rounded, calm hovers,
comfortable padding — while staying precise enough to read as instruments. Lead
with warmth; keep the tabular discipline.

### Buttons
- **Shape:** Gently rounded (8px), 34px control height.
- **Primary** (`.fb-btn`): Solid Signal Indigo, white text, 0 18px padding,
  weight 600–700.
- **Hover / Focus:** Soft brighten (`filter: brightness(1.1)`) and a 1px
  press-down on `:active`. Transitions 0.15s.
- **Ghost** (`.fb-link`): Transparent/panel background, muted text, hairline
  border; on hover the text shifts to Indigo Soft and the border to Signal
  Indigo.

### Chips & Toggles
- **Amenity chip:** Panel background, muted text, full-pill radius, 1px border —
  quiet metadata.
- **Toggle chip** (`.toggle-chip`): A styled checkbox; when on, fills with the
  Accent Glow wash, Signal Indigo border, and a check in an indigo box.
- **Badges / pills:** Pill or 5px radius. Status pills use a 12%-tint of their
  status hue as background with the solid hue as text (e.g. green-tint +
  Signal Green).

### Cards / Containers
- **Corner Style:** 12px (containers), 10px (hotel cards).
- **Background:** Panel, with Panel Raised for inner tiles (detail grid).
- **Shadow Strategy:** Flat at rest (resting-card shadow only on standalone
  cards); hotel cards lift to the Lifted shadow + -3px on hover with a 1.05
  image zoom.
- **Border:** 1px Line, always.
- **Internal Padding:** 22px (card), 13–14px (hotel card body).

### Inputs / Fields
- **Style:** Panel Raised background, 1px Line border, 8px radius, 34px height.
- **Focus:** Border shifts to Signal Indigo plus the indigo focus ring. No
  outline removal without the ring replacing it.
- **Labels:** Uppercase tracked Label type, stacked above the control.

### Navigation
- **Top bar** (`.topbar`): 52px, Panel background, hairline bottom border. Brand
  lockup (indigo icon tile + label) divided from the tabs by a vertical rule.
- **Tabs** (`.tab`): Muted by default; hover/active fill with Panel Raised. The
  active tab carries a short Signal Indigo underline (desktop) or a background
  highlight (mobile, where the bar scrolls horizontally).
- **Nav progress bar:** A fixed 3px Signal Indigo bar with an indigo glow that
  animates on internal navigation.

### Signature: The FIDS Table
- **The flight-information board** (`table.fids`): Panel background, Panel
  Raised header row with an Indigo Soft uppercase label and a Signal Indigo
  bottom rule. Rows divide on Line Soft and wash with Accent Glow on hover.
- **Remarks** carry a status hue *and* a word (Landed, Boarding, Delayed,
  Estimated, Departed) — never color alone.
- **STA/ETA** are heavy tabular figures; ETA is Caution Yellow.

## 6. Do's and Don'ts

### Do:
- **Do** keep Signal Indigo (#6366f1) rare — actions, focus, active state only.
- **Do** set every compared number in `tabular-nums`.
- **Do** separate surfaces with 1px Line borders and tonal layering (Void →
  Panel → Panel Raised); save shadows for hover/focus/float states.
- **Do** pair every status color with a text label (the FIDS remark pattern), so
  meaning never rests on hue alone.
- **Do** keep the indigo focus ring (`0 0 0 3px rgba(99,102,241,.25)`) on every
  focusable control.
- **Do** favor soft, approachable geometry — gentle radii, calm 0.15s
  transitions, comfortable padding.
- **Do** verify Muted (#7c829a) text clears 4.5:1 against its panel; bump toward
  Ink (#eef0f6) if it's close.

### Don't:
- **Don't** use cream/sand/parchment backgrounds, gradient text, hero-metric
  templates, or identical icon+heading+text card grids (generic AI-SaaS slop).
- **Don't** put a tiny uppercase tracked eyebrow above every section. Uppercase
  tracking is for control/column labels only.
- **Don't** use `border-left`/`border-right` greater than 1px as a colored
  accent stripe on cards, rows, or alerts (heavy-enterprise admin tell). Use
  full hairline borders or a background tint.
- **Don't** add glassmorphism or decorative gradients that fight legibility
  (over-designed marketing). The one sanctioned blur is the small hotel-card
  star badge.
- **Don't** introduce a new accent or a new status hue, or reuse a status hue
  for a different meaning. The palette is a closed set.
- **Don't** strip a focus outline without replacing it with the indigo ring.
