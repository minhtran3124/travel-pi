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

- Rule 1 — Fixed pre-existing undefined `bg-surface` token in `ChatPanel.tsx` (no `--color-surface` exists) → `bg-panel-raised`. Commit `35ba0c0`.
- Rule 1 — PLAN bug: it prescribed `text-on-accent` for `bg-ink` fills, but `on-accent` is dark in both themes → dark-on-dark (invisible) in light mode on the *inverting* ink fill. Added an `--on-ink` token (white→near-black) and pointed the 6 ink-fill spots at `text-on-ink`. Commits `82be8f2`, `e7a790f`, `35ba0c0`.
- Rule 1 — `bg-lime text-ink` badges (InterruptPrompt check, ChatLauncher button) are low-contrast in dark → `text-on-accent`. Commit `da31d28`.
- Rule 2 — `ChatLauncher.tsx` (floating chat button) was outside the planned 6-file chat sweep but is a primary chatbot surface; fixed its lime contrast. Commit `da31d28`.
- Rule 2 — **PLAN file-list gap**: finished the dark-mode sweep on UI + chat spots the plan omitted: Card/TripCard/control hover border `#e0e0e0`→`border-faint`; TripCard/TripHeader `ring-black/5`→`ring-line`; AppShell mobile nav `bg-subtle` (undefined no-op)→`bg-panel-raised`; ChatPanel amber error banner→`status-estimated`; auth success banners `bg-[#eaf7ee]`→`bg-status-confirmed/10`. Commit `3e51e50`.

**PLAN gaps surfaced:** (a) the sweep file-list was incomplete — a complete pass must grep all of `apps/web/src`, not a fixed list; (b) the ink-fill text token (`on-ink`) was missing from the token design.

### Known follow-ups (not done — need a decision)

- `SavedPlaceCard.tsx` category avatar tints (3 hardcoded blue/purple/teal `bg-[#…]` pairs) stay light-only — needs a dark category-tint palette (design input). Other 2 tints already tokenised.
- `Modal.tsx` overlay scrim `bg-[#1c1c1c]/40` left hardcoded **intentionally** — a dark dim is correct in both themes.
- e2e env gotcha: the Next dev server's Supabase middleware crashes without `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`; e2e was run with dummy values (theme specs need no backend). Affects `trip-smoke` too.

### Verify

Run from the worktree `apps/web` with Node v24 (`export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`).

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| FE typecheck | `pnpm exec tsc --noEmit` | 0 | clean |
| FE lint | `pnpm lint` (eslint) | 0 | clean |
| Theme e2e | `pnpm e2e -g "theme"` (dummy SUPABASE_* env) | 0 | 5/5 pass: OS-default dark+light, toggle+localStorage, reload-persist, no-FOUC (falsifiable @ domcontentloaded) |
| Unit suite | `pnpm test` | 1 | 50/52 pass; the 2 failures are **pre-existing** in `useAgentStream.stream.test.tsx` (streaming hook, PR #42), unrelated to this diff — confirmed by stashing this work and re-running |

### Rollback

- `git revert <sha>` per commit — all reversible; FE-only, no migration, no backend change.
- Whole feature: the branch is `feat/light-dark-mode-clean` off `v3`; abandon by not merging.

### Harness-Delta

- none
