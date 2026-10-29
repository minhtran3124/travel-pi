---
name: Travel Planner
description: A lively, capable trip-planning app — soft paper-toned pages, one electric accent, an AI agent that does the work.
colors:
  ink: "#1d1a15"
  departure-lime: "#cbf24a"
  departure-lime-soft: "#e6f8a8"
  coral: "#fb7755"
  coral-soft: "#ffe9e2"
  coral-ink: "#b4321f"
  on-accent: "#1c1c1c"
  on-ink: "#ffffff"
  ink-hover: "#2e2a23"
  void: "#f4f1ea"
  panel: "#fbf9f4"
  panel-raised: "#ece7dc"
  line: "#d9d3c6"
  line-soft: "#e6e0d3"
  scrim: "#1c1c1c"
  muted: "#5e584d"
  faint: "#857f72"
  status-confirmed: "#16a34a"
  status-estimated: "#ca8a04"
  status-delayed: "#ea580c"
  status-boarding: "#0284c7"
  status-cancelled: "#dc2626"
  status-hotel: "#2563eb"
# Dark palette — hand-tuned for dark surfaces (shipped via next-themes class
# dark mode; see §2 → Dark Mode). Only the tokens that flip are listed; radii,
# spacing, and typography are identical in both themes.
colorsDark:
  departure-lime: "#cbf24a"
  departure-lime-soft: "#2e3a12"
  coral: "#fb7755"
  coral-soft: "#3a201a"
  coral-ink: "#fb9a7e"
  on-accent: "#15161a"
  on-ink: "#15161a"
  void: "#1b1e24"
  panel: "#242832"
  panel-raised: "#2e333e"
  line: "#3b414d"
  line-soft: "#2f343f"
  scrim: "#000000"
  ink: "#f2f2f0"
  ink-hover: "#d8d8d4"
  muted: "#9aa0a8"
  faint: "#6b7079"
  status-confirmed: "#4ade80"
  status-estimated: "#fbbf24"
  status-delayed: "#fb923c"
  status-boarding: "#38bdf8"
  status-cancelled: "#f87171"
  status-hotel: "#60a5fa"
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
  dialog:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "16px"
---

# Design System: Travel Planner

## 1. Overview

**Creative North Star: "The Lively Field Guide"**

This is a trip-planning app that feels like a fresh field notebook in the hands of a
well-traveled friend who happens to be brilliant at logistics. Pages are soft paper
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
- Soft paper panels (`#fbf9f4`) on a warm off-white page (`#f4f1ea`) — no large pure-white surfaces.
- Near-black ink (`#1d1a15`) for primary text *and* primary actions — one strong voice.
- Exactly one accent: Departure Lime (`#cbf24a`), used sparingly for active/selected/highlight.
- Hairline borders, soft two-layer shadows, generous radii (10–20px).
- One typeface — Inter — across headings, labels, body, and data.
- Crisp, state-driven motion (150–200ms); nothing choreographed, nothing decorative.
- A hand-tuned **dark theme** (soft charcoal, not black) that flips every color token
  while radii, spacing, and type stay put (see §2 → Dark Mode).

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
  **Coral Soft** (`#ffe9e2`) is its tint; **Coral Ink** (`#b4321f`) is the only shade
  legible as *text* on paper (AA). Coral does **not** compete with lime: lime means
  *active/selected/go-here*; coral just adds warmth. Keep it off buttons and off any
  state indicator.

### Neutral
- **Ink** (`#1d1a15`): Primary text and the primary-action fill. Doing double duty as
  both "the words" and "the strong button" is intentional — it keeps one confident voice.
- **Muted** (`#5e584d`): Secondary text, inactive nav, captions. AA-safe on every paper surface (≥5.7:1).
- **Faint** (`#857f72`): Tertiary text and placeholders only. Never body copy.
- **Void** (`#f4f1ea`): The page background — warm paper, matching the API dashboard's Daylight theme.
- **Panel** (`#fbf9f4`): Soft paper for cards, header, modals, and raised panels.
- **Panel Raised** (`#ece7dc`): Inputs, selects, and secondary fills — the second neutral
  layer that separates controls from content.
- **Line** (`#d9d3c6`) / **Line Soft** (`#e6e0d3`): Hairline borders and faint dividers.
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

**The No-Glare Rule.** The page is `#f4f1ea` and cards are `#fbf9f4` — never pure `#ffffff`
for a large surface. Pure white glares over long sessions; keep the paper tone, and keep
the page→card step and the `line` border visible. (Supersedes the earlier No-Cream Rule.)

### Dark Mode

Dark mode has shipped (`next-themes`, class strategy: `dark:` utilities under a `.dark`
root; toggled from the nav). Every color token flips; radii, spacing, and typography do
not. In `apps/web/src/app/globals.css` the flip is done with **`@theme inline` var
indirection** — each Tailwind color token (`--color-panel`, `--color-ink`, …) points at a
bare CSS var (`--panel`, `--ink`, …) redefined under `:root` (light) and `.dark` (dark);
`--shadow-card` / `--shadow-lift` flip the same way. The dark surfaces are a **soft
charcoal** ladder (page `#1b1e24` → panel `#242832` → raised `#2e333e`), *not* black —
and because the soft-black card shadow nearly vanishes on dark, **borders carry the
elevation** there (line hardens to `#3b414d`). Lime and coral hues hold; their *soft*
tints and the status/topic spectrum are re-tuned to stay AA on dark. Author every surface
with tokens (`bg-panel`, `text-ink`, `border-line`) so it themes for free — a raw hex or
a hardcoded `#fff` breaks in dark.

### Named Rules
**The On-Ink-vs-On-Accent Rule.** Two "text-on-fill" tokens exist and they are *not*
interchangeable. **on-accent** is text on the **lime** fill — it stays dark ink in both
themes (lime never darkens). **on-ink** is text on the **ink action** fill — and because
ink itself inverts between themes (near-black in light, near-white in dark), on-ink must
invert with it (`#fff` light → `#15161a` dark) to stay legible. Put `text-on-ink` on ink
buttons and `text-on-accent` on the lime launcher/badge; swapping them fails in one theme.

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
- **Primary:** Ink fill (`#1d1a15`), white text. Hover darkens to `#2e2a23`. This is the
  commit action.
- **Ghost:** Panel fill, ink text, hairline `line` border. Hover fills to `panel-raised`
  (`#ece7dc`). The secondary/cancel action.
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
- **Background:** Panel paper (`#fbf9f4`) on the Void page.
- **Border:** 1px `line` (`#d9d3c6`).
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
- **Style:** `panel-raised` fill (`#ece7dc`), 1px `line` border, `10px` radius, `text-sm`
  ink text. Each control wears a uppercase **Label** caption above it (`gap-xs`).
- **Placeholder:** `muted` (`#5e584d`) — never lighter; placeholders must stay readable.
- **Focus:** Global neutral focus ring — `box-shadow: 0 0 0 3px rgba(29,26,21,0.16)`,
  `outline: none`. The same ring on every focusable element; the accent is *not* the focus color.

### Progress & Empty State
- **`ui/Meter`:** a slim spent-vs-cap bar (budget). Ink fill on a `panel-raised` track;
  once spend passes the cap the fill saturates to `status-cancelled` red — **never lime**
  (lime stays the active signal, so budget progress is drawn in ink/red). It is decorative
  (`aria-hidden`); the adjacent figures carry the accessible value.
- **`ui/EmptyState`:** the shared icon + title + hint + optional action block for empty
  lists and zero-data screens — the one place a friendly stroke glyph and a nudge live.

### Modals & Dialogs
There is **one** modal primitive — `ui/Modal` — and everything overlaying the page is
built on it. It carries the shared chrome so no screen re-invents it: a dimmed backdrop
(`#1c1c1c` at 40% + `backdrop-blur-sm`), a centered Panel-paper surface with a 1px `line`
border, large radius (`20px`, `rounded-lg`), `shadow-lift`, and `16px` (`p-lg`) padding,
entering with the `tp-pop` pop (`0.16s ease-out`). It **traps focus**, restores focus to
the trigger on close, and dismisses on both Esc and backdrop click. The title is Headline
(extrabold `1.1rem`). Width is the explicit `max-w-[28rem]` — never `max-w-md`, which the
`--spacing-md` token collapses to 12px under Tailwind v4.
- **`ui/ConfirmDialog`:** the yes/no confirmation, composed on `Modal`. Body copy is
  `text-sm` `muted`; the footer is `flex justify-end gap-sm` with a **ghost Cancel** and a
  **primary (ink) confirm** — the same two-button footer every modal uses (see
  `NewTripModal`). Use it for any destructive or irreversible prompt.
- **Named Rule — The No-Native-Dialog Rule.** `window.confirm`, `window.alert`, and
  `window.prompt` are **forbidden** in product UI. They render the browser's chrome
  (unstyled, unbranded, no focus trap, no tokens) — the exact off-brand box this system
  exists to replace. Reach for `ConfirmDialog` (or `Modal`) instead, always.

### Navigation
- **Style:** A single top bar — `panel` background, hairline bottom border, `56px` tall
  (`h-14`), centered to a `max-w-5xl` column. On the left, an ink-on-lime plane-mark badge
  + bold wordmark, then bold `text-sm` links: **Trips · Places · Flights · Hotels ·
  Bookings**. Right-aligned cluster: **LocaleSwitcher** (en/vi), **ThemeToggle** (a
  `rounded-pill` sun/moon icon button), and the **UserMenu** avatar. Below `sm` the links
  collapse into a hamburger dropdown.
- **States:** Active link is ink over a 2px lime underline; inactive is `muted` and
  brightens to ink on hover. `aria-current="page"` marks the active route.
- **Tabs:** A bottom-border tablist — the active tab is ink text over a **Departure Lime**
  2px underline; inactive tabs are muted with a transparent underline. This is one of the
  few load-bearing uses of lime in the UI.

### Chat Launcher & Panel (signature component)
- **Launcher:** A `56px` circular **Departure Lime** FAB pinned bottom-right, ink chat
  icon, `shadow-lift`. Toggles to an × when open; `brightness-105` on hover, press on
  active. This is the app's single most expressive use of the accent — the agent waving hello.
- **Panel:** A floating `panel` surface (`ChatPanel`) carrying the streaming conversation.
  On desktop it floats bottom-right; on mobile (`isCompact`) it becomes a full **responsive
  sheet** — an `aria-modal` dialog that traps focus, closes on Esc, and locks body scroll.
  Its header (`ChatHeader`) shows the agent avatar, a ready/working/waiting status, and a
  gear **settings menu** (New conversation); a **Stop** control interrupts a run in flight.
  Keep it clean, keep the user oriented, keep every agent action visible and reversible.

### Agent Surface Vocabulary (inside the panel)
The chat is where the energetic personality is fully expressed, so it has its own small
component set — all still built from tokens and the shared primitives:
- **Activity trail (`AgentActivityTrail`):** the agent's work made visible — tool steps
  grouped into human "family" labels (hotels, flights, weather, places…), a soft pulsing
  `tp-trail-dot` while a step runs, and a check when it lands. Never shows raw tool names.
- **Result chips + side panel:** finished tool output attaches as inline **result cards
  /chips** (`ResultChips`, `tp-card-in`) that open a **`SidePanel`** — a detail drawer that
  springs out to the *left* of the chat (a bottom sheet in compact mode) with **one tab per
  renderable panel**, so several places categories each get their own tab. Panel kinds:
  route (lazy MapLibre map), places, weather, air quality, flights, hotels.
- **Interrupt prompt (`InterruptPrompt`):** the HITL checkpoint (e.g. plan approval, a
  booking to confirm) shown in place of the composer. **Lime** marks the moment the agent
  hands control back — "in control, never managed" made visible — and nothing proceeds
  until the user approves or rejects.
- **Follow-up suggestions (`ChatSuggestions`):** a scrollable rail of pill chips riding the
  composer, offering next prompts by flow. Bare chips, no band.
- **Reply feedback (`MessageFeedback` + `FeedbackDialog`):** thumbs up/down on each
  assistant reply; a thumbs-down opens a small Modal for a reason code + optional comment.
- **Panel i18n:** side panels render under a **separate nested intl provider** keyed on the
  backend-detected `panelLanguage`, which may differ from the app locale.

### Browse & Trip Surfaces
Surfaces the manual UI added alongside the agent (agent-native parity — everything here the
agent can also drive): **Flights** and **Hotels** browse pages (`FlightResultCard` /
`HotelResultCard`), a **destination guide** (`/guide/[city]`) with a **trip map**
(`TripMap`, lazy MapLibre), and a **Today tab** on the in-progress trip (weather, air
quality, directions for the day). All compose `Card` / `Pill` / `EmptyState` and the tokens
— no new chrome.

## 6. Do's and Don'ts

### Do:
- **Do** keep Departure Lime (`#cbf24a`) to ≤10% of any screen, and only for active /
  selected / highlight / the chat launcher. Rarity is the signal.
- **Do** make the primary action ink (`#1d1a15`) and use lime only to mark state.
- **Do** build hierarchy from Inter's weights (400→800) and the fixed rem scale — one
  typeface only.
- **Do** rest surfaces on hairline `line` borders and reserve `shadow-lift` for hover,
  modals, and the launcher.
- **Do** keep body and placeholder text at `muted` (`#5e584d`) or darker for AA — never
  `faint` for anything a user must read.
- **Do** give every interactive control its full state set (default, hover, focus, active,
  disabled) and the global focus ring.
- **Do** keep motion crisp and state-driven (150–200ms); honor `prefers-reduced-motion`
  on every animation.
- **Do** build every new component out of the shared `ui/` primitives (`Button`, `Card`,
  `Modal`, `ConfirmDialog`, `Field`, `Select`, `Textarea`, `Tabs`, `Pill`, `Meter`,
  `EmptyState`, `Spinner`) and the design tokens (`bg-panel`, `border-line`,
  `text-ink`/`muted`, the `xs–xl` spacing scale, `rounded-{sm,md,lg,pill}`). Extend the
  system before inventing a one-off; a new element that doesn't cite this doc is a bug.

### Don't:
- **Don't** build a **generic SaaS dashboard** — no card-grid sea, no gray-on-white, no
  hero-metric template, no identical icon+heading+text tiles.
- **Don't** drift toward a **corporate OTA** — no ad banners, no fake-urgency badges
  ("2 left at this price!"), no clutter-for-density.
- **Don't** go **childish or over-gamified** — no mascots, no confetti, no cartoon badges.
  Playful stays grown-up.
- **Don't** ship a **cold enterprise tool** — warmth and personality are required.
- **Don't** use pure `#ffffff` for large surfaces (page, cards, header). Use the paper
  tones `#f4f1ea` / `#fbf9f4`. (The No-Glare Rule.)
- **Don't** use a lime fill for a primary button, a lime surface, or lime as decoration.
- **Don't** use uppercase letter-spacing anywhere but form labels — no tracked eyebrows.
- **Don't** add a second typeface or a display font for UI labels, buttons, or data.
- **Don't** put a hard, dark drop shadow on anything (the 2014 Test). Shadows are wide,
  soft, and low-opacity.
- **Don't** use `window.confirm` / `alert` / `prompt`, or hand-roll a bespoke overlay.
  Use `ConfirmDialog` / `Modal` (the No-Native-Dialog Rule) — native browser dialogs are
  unstyled, unbranded, and break the focus/motion contract.
