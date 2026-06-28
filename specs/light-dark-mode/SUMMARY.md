# light-dark-mode — Summary

Lane: normal
Confidence: high
Reason: FE-only theming addition; one risk flag (existing UI behavior changes) plus weak UI-test proof. No hard gate (no auth/data/migration/external/validation/high-blast file).
Flags: existing-behavior, weak-proof
Affects: apps/web theming tokens (globals.css `@theme`), root layout, shared UI surfaces + chatbot panel
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

support light/dark mode cho UI and chatbot

<!-- Direction confirmed via /feature-intake AskUserQuestion (3 forks, all resolved to the
     recommended option); user-confirmed scope decisions, captured here so the intent oracle
     stays independent of PLAN.md: -->

- **Implementation/persistence:** `next-themes` + class strategy — `ThemeProvider attribute="class"` toggles a `.dark` class on `<html>`, persists `theme` in `localStorage`, suppresses SSR flash.
- **Default mode (first-time visitor):** follow OS preference (`defaultTheme="system"`, `enableSystem`); the toggle overrides and persists.
- **Dark palette source:** hand-design a proper dark token set — dark surfaces, ink flip, status/topic spectrums re-tuned for AA contrast on dark, softened shadows (not a quick auto-invert).

## What changed

Not yet implemented — intake only. Planned: add light/dark theming to the Next.js web app
(`apps/web`), covering the main UI and the chatbot panel. The app currently ships a single
hand-tuned light theme as Tailwind v4 `@theme` semantic tokens (`--color-void`, `--color-panel`,
`--color-ink`, status/topic spectrums) with no theme provider and zero `dark:` usage.

### Rationale

The codebase already routes all color through **named semantic tokens**, so dark mode is best
added by redefining those tokens under a `.dark` selector (TW v4 `@theme inline` → CSS vars on
`:root` / `.dark`) rather than scattering `dark:` variants across components. `next-themes` is
the standard, low-friction switcher for Next App Router + shadcn (already configured,
`components.json` present) and handles the SSR no-flash problem. System-default matches user
expectation while keeping manual override.

### Alternatives considered

- *Custom class-toggle context* — rejected: re-implements next-themes' no-flash script and
  matchMedia handling for no benefit.
- *Cookie + server-rendered theme* — rejected: extra plumbing; class strategy's inline script
  already prevents flash and is the shadcn-documented path.
- *Quick auto-invert dark palette* — rejected by user in favour of a hand-tuned dark token set
  with AA-correct status/topic colors.

### Deviations

- none

### Verify

<!-- Filled at execution time; commands not yet run (intake stage). -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| FE typecheck | `cd apps/web && pnpm --filter web typecheck` (Node v24) | — | not yet run (intake stage) |
| FE lint | `cd apps/web && pnpm --filter web lint` (Node v24) | — | not yet run |
| Theme toggle behavior | Playwright/manual: toggle persists across reload, `.dark` on `<html>`, no FOUC | — | not yet run |

### Rollback

- `git revert <sha>` per task — all reversible; no migration, no backend change.

### Harness-Delta

- none
