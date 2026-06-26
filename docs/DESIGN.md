# DESIGN.md — Travel Planner web (`apps/web`)

The visual system for the Next.js frontend. Source of truth for tokens lives in
`apps/web/src/app/globals.css` (`@theme`); this doc explains intent and usage.

## Direction

Clean, light, modern travel-app UI. White surfaces, near-black ink for primary
actions, a single bright **chartreuse** accent used sparingly for highlights and
active state. Hairline borders, soft shadows, generous radii. Calm by default;
the lime is the one place the brand "pops."

Register: **product** (design serves the task). Color strategy: **restrained** —
tinted neutrals + one accent well under 10% of surface.

## Palette (light)

| Role | Token | Value | Use |
|---|---|---|---|
| Page bg | `--color-void` | `#f7f7f5` | app background |
| Surface | `--color-panel` | `#ffffff` | cards, header, dialogs, panels |
| Fill | `--color-panel-raised` | `#f4f4f2` | inputs, secondary fills |
| Hairline | `--color-line` | `#ececec` | borders, dividers |
| Faint divider | `--color-line-soft` | `#f1f0ee` | low-emphasis separators |
| Ink (primary) | `--color-ink` | `#1c1c1c` | primary text **and** primary-action bg |
| Muted | `--color-muted` | `#6b6b6b` | secondary text |
| Faint | `--color-faint` | `#9a9a9a` | placeholders, tertiary |
| Accent | `--color-lime` | `#cbf24a` | active tab, FAB, status dot, highlights |
| Accent soft | `--color-lime-soft` | `#e6f8a8` | pale lime washes |

**Primary action = ink, not the accent.** Buttons/CTAs are near-black with white
text (`Button` `primary`); the lime is reserved for active/affordance cues so it
keeps its signal. There is intentionally **no coral/orange brand** anymore (the
old dark theme's `coral-*` tokens were removed).

Status spectrum (`--color-status-*`) and the topic palette (`--color-topic-*`)
are tuned darker for AA contrast on light surfaces; `Pill` renders them as a pale
tint of the hue + darkened label + hairline ring.

## Geometry & elevation

- Radii: `--radius-sm 10px` (inputs, buttons), `--radius-md 16px` (cards),
  `--radius-lg 20px` (dialogs), `--radius-pill` (chips, FAB, send).
- Shadows: `--shadow-card` (resting cards), `--shadow-lift` (hover, dialogs,
  FAB) — both soft, light-theme tuned.
- Spacing steps: `xs 4 / sm 8 / md 12 / lg 16 / xl 24`.

## Gotchas

- **Never use `max-w-{xs,sm,md,lg,xl}`.** The named spacing tokens shadow
  Tailwind v4's container scale, so `max-w-md` resolves to `12px`. Use arbitrary
  values, e.g. `max-w-[28rem]`. (See `Modal.tsx`.)
- Class merging goes through `cn()` (`@/lib/cn`); shared control chrome lives in
  `components/ui/control.ts` (`labelClass`, `controlClass`).

## Primitives (`components/ui`)

`Button` (primary=ink / ghost=white-bordered) · `Field` / `Select` / `Textarea`
(labelled controls) · `Card` (bordered white, lift on hover) · `Modal`
(white dialog, dimmed scrim) · `Tabs` (lime active underline) · `Pill`
(tinted status/topic chip) · `Spinner` · `EmptyState`.

## Typography

`Inter` (variable, via `next/font`) across UI and body; weight carries
hierarchy (400/500 body, 700/800 headings). Mono `Menlo` for times/codes.
