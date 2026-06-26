---
name: Travel Planner
description: A lively, capable trip-planning app — clean white pages, one electric accent, an AI agent that does the work.
colors:
  ink: "#1c1c1c"
  departure-lime: "#cbf24a"
  departure-lime-soft: "#e6f8a8"
  coral: "#fb7755"
  coral-soft: "#ffe9e2"
  coral-ink: "#c2410c"
  on-accent: "#1c1c1c"
  void: "#f7f7f5"
  panel: "#ffffff"
  panel-raised: "#f4f4f2"
  line: "#ececec"
  line-soft: "#f1f0ee"
  muted: "#6b6b6b"
  faint: "#9a9a9a"
  status-confirmed: "#16a34a"
  status-estimated: "#ca8a04"
  status-delayed: "#ea580c"
  status-boarding: "#0284c7"
  status-cancelled: "#dc2626"
  status-hotel: "#2563eb"
typography:
  headline:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.1rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
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
rounded:
  sm: "10px"
  md: "16px"
  lg: "20px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.panel}"
    rounded: "{rounded.sm}"
    padding: "0 18px"
    height: "34px"
  button-primary-hover:
    backgroundColor: "#2e2e2e"
    textColor: "{colors.panel}"
  button-ghost:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 18px"
    height: "34px"
  button-ghost-hover:
    backgroundColor: "{colors.panel-raised}"
    textColor: "{colors.ink}"
  card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "16px"
  input:
    backgroundColor: "{colors.panel-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 8px"
    height: "34px"
  pill:
    rounded: "{rounded.pill}"
    padding: "1px 8px"
  tab-active:
    textColor: "{colors.ink}"
  chat-launcher:
    backgroundColor: "{colors.departure-lime}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.pill}"
    height: "56px"
    width: "56px"
---

# Design System: Travel Planner

## 1. Overview

**Creative North Star: "The Lively Field Guide"**

This is a trip-planning app that feels like a fresh field notebook in the hands of a
well-traveled friend who happens to be brilliant at logistics. Pages are clean white
spreads; the structure is hairline-thin and quiet, so the content — destinations,
itineraries, bookings, the AI agent's work — is what carries the energy. A single
electric chartreuse, **Departure Lime**, is the trail-marker that highlights what's
active, what's selected, and where to go next. The liveliness comes from that decisive
accent, from crisp motion, and from the agent visibly doing real work — never from
clutter, color noise, or decoration.

The personality is *energetic, playful, friendly* held inside a *capable, not corporate*
frame. It is grown-up playful: warm and quick, never juvenile. There are no mascots, no
confetti, no gamified badges. Delight is earned in small systematic moments — a
confirmation landing, a card lifting under the cursor, the agent returning a result —
not sprayed across the page.

This system explicitly rejects four neighbors. It is **not a generic SaaS dashboard**
(no card-grid sea, no gray-on-white, no hero-metric template). It is **not a corporate
OTA** (no ad banners, no fake-urgency badges, no cluttered density-for-its-own-sake). It
is **not childish or over-gamified**. And it is **not a cold enterprise tool** (warmth
and personality are required, not optional).

**Key Characteristics:**
- Clean white panels (`#ffffff`) on a barely-warm off-white page (`#f7f7f5`).
- Near-black ink (`#1c1c1c`) for primary text *and* primary actions — one strong voice.
- Exactly one accent: Departure Lime (`#cbf24a`), used sparingly for active/selected/highlight.
- Hairline borders, soft two-layer shadows, generous radii (10–20px).
- One typeface — Inter — across headings, labels, body, and data.
- Crisp, state-driven motion (150–200ms); nothing choreographed, nothing decorative.

## 2. Colors

A near-monochrome ink-and-paper foundation, lit by a single electric accent and a
disciplined set of semantic status hues.

### Primary
- **Departure Lime** (`#cbf24a`): The one brand color and the system's trail-marker. It
  carries the active tab underline, the floating chat launcher (the agent's "I'm here"
  signal), selected/active states, and the rare deliberate highlight. **Departure Lime
  Soft** (`#e6f8a8`) is its pale companion for low-emphasis tints. Lime is a *signal*,
  never a surface and never decoration.

### Warm secondary
- **Coral** (`#fb7755`): A warm, friendly secondary that carries *travel warmth* — used
  only as decoration and tint, never as a signal or an action. Today it appears in the
  location-pin glyph, the destination-cover trails, and the welcome-strip flight arc.
  **Coral Soft** (`#ffe9e2`) is its tint; **Coral Ink** (`#c2410c`) is the only shade
  legible as *text* on white (AA). Coral does **not** compete with lime: lime means
  *active/selected/go-here*; coral just adds warmth. Keep it off buttons and off any
  state indicator.

### Neutral
- **Ink** (`#1c1c1c`): Primary text and the primary-action fill. Doing double duty as
  both "the words" and "the strong button" is intentional — it keeps one confident voice.
- **Muted** (`#6b6b6b`): Secondary text, inactive nav, captions. AA-safe on white/paper.
- **Faint** (`#9a9a9a`): Tertiary text and placeholders only. Never body copy.
- **Void** (`#f7f7f5`): The page background — a barely-warm off-white, *not* cream.
- **Panel** (`#ffffff`): Pure white for cards, header, modals, and raised panels.
- **Panel Raised** (`#f4f4f2`): Inputs, selects, and secondary fills — the second neutral
  layer that separates controls from content.
- **Line** (`#ececec`) / **Line Soft** (`#f1f0ee`): Hairline borders and faint dividers.
  Structure is drawn at 1px; it frames, it never shouts.

### Semantic (status + topic)
- **Status spectrum** — Confirmed green (`#16a34a`), Estimated amber (`#ca8a04`), Delayed
  orange (`#ea580c`), Boarding cyan (`#0284c7`), Cancelled red (`#dc2626`), Hotel blue
  (`#2563eb`). Tuned for AA on light surfaces and rendered only inside Pills (a pale tint
  of the hue behind a darkened-hue label), never as large fills.
- **Topic palette** — A parallel nine-hue family (transport, money, safety, culture, food,
  connectivity, health, etiquette, language) used the same Pill way to tag agent answers
  by subject. Each is pre-darkened for light surfaces.

### Named Rules
**The One Signal Rule.** Departure Lime appears on ≤10% of any screen and only where it
means *active, selected, or go-here*. Its rarity is the entire point — the moment lime
becomes a background or a decoration, the signal is dead.

**The Ink-Is-The-Button Rule.** The primary action is ink, not lime. Lime marks state;
ink commits. Never invert this — a lime "Save" button breaks the whole color logic.

**The No-Cream Rule.** The page is `#f7f7f5` — a near-neutral off-white. Never warm it
toward beige/sand/parchment. Warmth lives in copy and content, never in the body fill.

## 3. Typography

**Body & Display Font:** Inter (with `system-ui, sans-serif` fallback)
**Mono Font:** Menlo (with `Consolas, "SF Mono", monospace`) — code/data only, rarely surfaced.

**Character:** One humanist sans does everything. Hierarchy is built from *weight and
size*, not from a second face. This is deliberate product-UI discipline: many type
elements on a screen, so contrast comes from a tight scale and heavy-vs-regular weight,
never from display fonts dropped into labels.

### Hierarchy
- **Headline** (extrabold 800, `1.1rem`, line-height 1.2): Page and modal titles, empty-state
  headlines. The heaviest weight in the system; this is as loud as type gets.
- **Title** (bold 700, `1rem`, line-height 1.3): Section headers, card titles, the app
  wordmark in the nav.
- **Body** (regular 400, `0.875rem` / `text-sm`, line-height 1.5): Default reading and UI
  text. Cap prose at 65–75ch; data and compact UI may run denser.
- **Label** (bold 700, `0.68rem`, uppercase, letter-spacing `0.08em`, color Muted): The
  small caption above every form control. The *only* place uppercase tracking is allowed.

### Named Rules
**The Weight-Not-Face Rule.** Need emphasis? Change weight or size. Never reach for a
second typeface or a display font — Inter from 400 to 800 covers every need here.

**The Uppercase-Is-For-Labels-Only Rule.** Uppercase + letter-spacing belongs to form
labels and nothing else. No tracked all-caps eyebrows above sections, ever.

## 4. Elevation

A hybrid, mostly-flat system: surfaces rest on hairline borders and lift with soft,
two-layer shadows only in *response to state*. Depth is a reaction, not a default. Cards
sit flat-with-a-border at rest and rise on hover; modals and the chat launcher carry the
deeper lift because they genuinely float above the page.

### Shadow Vocabulary
- **Card** (`box-shadow: 0 1px 2px rgba(17,17,17,0.04), 0 6px 20px -8px rgba(17,17,17,0.10)`):
  The resting elevation for cards — a near-imperceptible settle, not a drop shadow.
- **Lift** (`box-shadow: 0 16px 40px -12px rgba(17,17,17,0.18), 0 4px 12px -6px rgba(17,17,17,0.10)`):
  The raised elevation for hovered cards, modals, and the chat launcher. Soft and wide,
  never hard or dark.

### Named Rules
**The Lift-On-State Rule.** Shadows deepen only on hover, float, or focus. A surface that
is shadowed at rest *and* on hover has nowhere to go — the motion is the meaning.

**The 2014 Test.** If a shadow looks like a hard gray drop shadow, it's wrong: blur is too
small and the tone is too dark. These shadows are wide, soft, and tinted near-black at low
opacity — they read as light, not as a border.

## 5. Components

Components are **crisp and quick**: tight hairline chrome, snappy 150ms transitions, a
small physical press (`active:translate-y-px`) and a small hover lift. Confident, fast,
never heavy.

### Buttons
- **Shape:** Small rounded (`10px`, `rounded-sm`), fixed `34px` height, `18px` side padding,
  bold `text-sm` label.
- **Primary:** Ink fill (`#1c1c1c`), white text. Hover darkens to `#2e2e2e`. This is the
  commit action.
- **Ghost:** White fill, ink text, hairline `line` border. Hover fills to `panel-raised`
  (`#f4f4f2`). The secondary/cancel action.
- **States:** `active:translate-y-px` press on both; `disabled` drops to 50% opacity with
  `not-allowed` cursor. Focus uses the global ring (see Inputs).

### Chips / Pills
- **Style:** Fully rounded (`rounded-pill`), `text-xs` bold. Built from one semantic hue:
  a 16%-tint background, a 70%-toward-black label of the same hue, and a 28%-tint inset
  ring. This keeps every status/topic tag AA-legible on white.
- **Variants:** `status` (booking states) and `topic` (agent-answer subjects); `best_time`
  is the one topic that borrows Departure Lime.

### Cards / Containers
- **Corner Style:** Medium rounded (`16px`, `rounded-md`).
- **Background:** Panel white (`#ffffff`) on the Void page.
- **Border:** 1px `line` (`#ececec`); hardens slightly to `#e0e0e0` on hover.
- **Shadow Strategy:** `shadow-card` at rest → `shadow-lift` on hover, paired with a
  `-translate-y-0.5` rise. See Elevation.
- **Internal Padding:** `16px` (`p-lg`).

### Destination Covers (trip postcards)
The Trips grid uses a **postcard** variant of the card: a full-bleed cover band
(`108px`) carrying a soft 135° gradient, a dotted **flight-path arc + plane** motif, a
frosted status pill, and a monogram chip straddling the cover seam (avatar-style). With
no real photos (mock backend), each trip's cover is chosen **deterministically from the
city/title hash** across six soft "horizon" palettes (sky, coral, sea, dawn, rose,
sunset) — warmth and variety without imagery. The covers are intentionally light (L
≈ 0.94–0.97) so the frosted chip and monogram stay legible. A *Happening now* trip
overrides to the **lime** cover + `ring-2 ring-lime` + lime monogram, so the One Signal
Rule still carries on the home grid. This is the load-bearing place where the energetic/
friendly personality lives — keep it a Trips signature, not a per-page default.

### Welcome Strip
The Trips landing opens with one **welcome strip**: a rounded `lg` band on a soft
sky→meadow→sunset horizon gradient with a faint coral flight arc, a friendly headline
("Where to next?"), a data-aware momentum line in the *well-traveled friend* voice
("Tokyo is happening right now — have a great trip"), and the primary CTA. It is the
home's single hero — do not repeat a gradient hero on every page (that reads heavy);
warmth on the other surfaces comes from the covers, copy, and the coral accent instead.

### Inputs / Fields
- **Style:** `panel-raised` fill (`#f4f4f2`), 1px `line` border, `10px` radius, `text-sm`
  ink text. Each control wears a uppercase **Label** caption above it (`gap-xs`).
- **Placeholder:** `muted` (`#6b6b6b`) — never lighter; placeholders must stay readable.
- **Focus:** Global neutral focus ring — `box-shadow: 0 0 0 3px rgba(28,28,28,0.16)`,
  `outline: none`. The same ring on every focusable element; the accent is *not* the focus color.

### Navigation
- **Style:** A single top bar — `panel` background, hairline bottom border, `56px` tall,
  centered to a `max-w-5xl` column. Bold wordmark on the left, bold `text-sm` links beside it.
- **States:** Active link is ink; inactive is `muted` and brightens to ink on hover.
  `aria-current="page"` marks the active route.
- **Tabs:** A bottom-border tablist — the active tab is ink text over a **Departure Lime**
  2px underline; inactive tabs are muted with a transparent underline. This is one of the
  few load-bearing uses of lime in the UI.

### Chat Launcher & Panel (signature component)
- **Launcher:** A `56px` circular **Departure Lime** FAB pinned bottom-right, ink chat
  icon, `shadow-lift`. Toggles to an × when open; `brightness-105` on hover, press on
  active. This is the app's single most expressive use of the accent — the agent waving hello.
- **Panel:** A floating white panel (the agent's surface) carrying the streaming
  conversation, quick replies, and human-in-the-loop interrupt prompts. It is the
  product's differentiator: keep it clean, keep the user oriented, keep every agent action
  visible and reversible.

## 6. Do's and Don'ts

### Do:
- **Do** keep Departure Lime (`#cbf24a`) to ≤10% of any screen, and only for active /
  selected / highlight / the chat launcher. Rarity is the signal.
- **Do** make the primary action ink (`#1c1c1c`) and use lime only to mark state.
- **Do** build hierarchy from Inter's weights (400→800) and the fixed rem scale — one
  typeface only.
- **Do** rest surfaces on hairline `line` borders and reserve `shadow-lift` for hover,
  modals, and the launcher.
- **Do** keep body and placeholder text at `muted` (`#6b6b6b`) or darker for AA — never
  `faint` for anything a user must read.
- **Do** give every interactive control its full state set (default, hover, focus, active,
  disabled) and the global focus ring.
- **Do** keep motion crisp and state-driven (150–200ms); honor `prefers-reduced-motion`
  on every animation.

### Don't:
- **Don't** build a **generic SaaS dashboard** — no card-grid sea, no gray-on-white, no
  hero-metric template, no identical icon+heading+text tiles.
- **Don't** drift toward a **corporate OTA** — no ad banners, no fake-urgency badges
  ("2 left at this price!"), no clutter-for-density.
- **Don't** go **childish or over-gamified** — no mascots, no confetti, no cartoon badges.
  Playful stays grown-up.
- **Don't** ship a **cold enterprise tool** — warmth and personality are required.
- **Don't** warm the page toward cream/sand/beige. The body is `#f7f7f5`, a near-neutral
  off-white. (The No-Cream Rule.)
- **Don't** use a lime fill for a primary button, a lime surface, or lime as decoration.
- **Don't** use uppercase letter-spacing anywhere but form labels — no tracked eyebrows.
- **Don't** add a second typeface or a display font for UI labels, buttons, or data.
- **Don't** put a hard, dark drop shadow on anything (the 2014 Test). Shadows are wide,
  soft, and low-opacity.
