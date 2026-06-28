---
slug: light-dark-mode
status: active
owner: Minh Tran
created: 2026-06-27
---

# Light / Dark Mode for UI + Chatbot — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to implement this plan task-by-task.

**Goal:** Add a user-toggleable light/dark theme across the `apps/web` UI and the chatbot, defaulting to the visitor's OS preference and persisting their choice.

**Architecture:** Drive theming entirely through the existing Tailwind v4 semantic tokens. Refactor `globals.css` from a static `@theme` block to `@theme inline` + CSS variables defined under `:root` (light) and `.dark` (dark), so every `bg-panel`/`text-ink`/etc. utility flips by swapping variables — no scattered `dark:` variants. `next-themes` (class strategy) toggles the `.dark` class on `<html>`, persists to `localStorage`, honors `prefers-color-scheme` by default, and runs an inline pre-paint script to prevent FOUC. A toggle in the app header (mirroring `LocaleSwitcher`) and a hardcoded-color sweep complete the coverage.

**Tech Stack:** Next.js 16.2.9 (App Router, RSC), Tailwind CSS v4 (`@theme`), `next-themes`, `next-intl`, vitest, Playwright. Node **v24** for all pnpm commands.

**Spec source:** `specs/light-dark-mode/SUMMARY.md` (design forks resolved at intake — no `design.md`/`research-brief.md` for this normal-lane feature).

---

## 1. Motivation

The web app ships a single hand-tuned light theme. Users on dark-mode OS settings get an unexpectedly bright UI, and there's no way to opt into dark. We add a first-class light/dark toggle covering both the main app surfaces and the chatbot panel.

## 2. Non-goals

- No backend / DB persistence of theme (localStorage only — no schema change).
- No per-component `dark:` variant utilities — theming flows through token swaps only.
- No redesign of the light theme; its values are preserved verbatim.
- No new icon dependency — toggle uses inline SVG like the existing `PlaneMark`/`GlobeMark`.

## 3. Success Criteria

- First-time visitor sees light or dark matching their OS (`prefers-color-scheme`); the header toggle overrides and persists across reloads (`localStorage` key `theme`).
- No flash of wrong theme on load (FOUC) — `.dark` is set on `<html>` before first paint.
- Chatbot panel + all app surfaces flip correctly; no white-on-white or unreadable contrast (notably the primary button and chat panel).
- `tsc --noEmit`, `eslint`, and `vitest` all pass; a Playwright spec proves toggle + persistence + no-FOUC.

## 4. Tasks

> Files are disjoint within each wave (per `wave-parallelism.md`). All pnpm commands assume Node v24:
> `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`.

### Task 1.1 — Add next-themes + ThemeProvider + layout wiring (wave 1)

```xml
<task id="1.1" wave="1">
  <files>apps/web/package.json, apps/web/src/components/theme/ThemeProvider.tsx, apps/web/src/app/layout.tsx</files>
  <action>
Add `next-themes` to apps/web dependencies (pnpm add next-themes --filter web; pin the resolved version).
Create `apps/web/src/components/theme/ThemeProvider.tsx` as a client component:
```tsx
"use client";
import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ReactNode } from "react";

export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
```
Wire into `apps/web/src/app/layout.tsx`: add `suppressHydrationWarning` to the `<html>` tag (required — next-themes mutates the class before hydration), and wrap the existing provider tree with `<ThemeProvider>` as the OUTERMOST provider inside `<body>` (so AppShell + ChatWidget both see it). Do not remove `NextIntlClientProvider`/`IdentityProvider`/`QueryProvider`; nest them inside ThemeProvider.
  </action>
  <verify>cd apps/web && pnpm install && pnpm exec tsc --noEmit</verify>
  <done>next-themes installed; ThemeProvider wraps the app; html has suppressHydrationWarning; typecheck passes.</done>
</task>
```

### Task 1.2 — Token-layer refactor + hand-tuned dark palette (wave 1)

```xml
<task id="1.2" wave="1">
  <files>apps/web/src/app/globals.css</files>
  <action>
Refactor the color layer of `globals.css` for runtime theme switching, preserving all light values verbatim.

1. Add the class-based dark variant escape hatch near the top (after the @import):
   `@custom-variant dark (&:where(.dark, .dark *));`

2. Convert the COLOR + SHADOW tokens in the `@theme` block to `@theme inline` indirection (keep radii/spacing/typography in a plain `@theme` block — they don't flip). For every flipping token, point the Tailwind token at a bare CSS var:
   `@theme inline { --color-void: var(--void); --color-panel: var(--panel); ... --shadow-card: var(--shadow-card-v); --shadow-lift: var(--shadow-lift-v); }`

3. Define the bare vars under `:root` (LIGHT — copy current hex values exactly) and `.dark` (NEW dark palette below). Map: void/panel/panel-raised/line/line-soft, ink/muted/faint, on-accent, lime/lime-soft, coral/coral-soft/coral-ink, all status-* and topic-*, plus shadow-card-v/shadow-lift-v, and a NEW `--ink-hover` (light: #2e2e2e, dark: #d8d8d4) consumed by Button in Task 2.3.

Dark palette (`.dark` block):
```css
.dark {
  --void: #0e0f12; --panel: #17191e; --panel-raised: #1f2228;
  --line: #2a2d33; --line-soft: #232529;
  --ink: #f2f2f0; --muted: #9aa0a8; --faint: #6b7079;
  --on-accent: #15161a; --ink-hover: #d8d8d4;
  --lime: #cbf24a; --lime-soft: #2e3a12;
  --coral: #fb7755; --coral-soft: #3a201a; --coral-ink: #fb9a7e;
  --status-confirmed: #4ade80; --status-estimated: #fbbf24; --status-delayed: #fb923c;
  --status-boarding: #38bdf8; --status-cancelled: #f87171; --status-hotel: #60a5fa;
  --topic-transport: #fbbf24; --topic-money: #4ade80; --topic-safety: #f87171;
  --topic-culture: #c4b5fd; --topic-food: #fb923c; --topic-connectivity: #38bdf8;
  --topic-health: #fb7185; --topic-etiquette: #2dd4bf; --topic-language: #a5b4fc;
  --shadow-card-v: 0 1px 2px rgba(0,0,0,0.40), 0 6px 20px -8px rgba(0,0,0,0.55);
  --shadow-lift-v: 0 16px 40px -12px rgba(0,0,0,0.65), 0 4px 12px -6px rgba(0,0,0,0.45);
}
```

4. Flip the two light-specific values OUTSIDE `@theme`:
   - Focus ring (`*:focus-visible`): make the ring color a var — `:root { --focus-ring: rgba(28,28,28,0.16); } .dark { --focus-ring: rgba(242,242,240,0.22); }` and reference `box-shadow: 0 0 0 3px var(--focus-ring);`.
   - The `body { background: var(--color-void); color: var(--color-ink); }` already flips — leave as is.

Do NOT change any light hex value, radius, spacing, or font token.
  </action>
  <verify>cd apps/web && grep -q '@custom-variant dark' src/app/globals.css && grep -q '@theme inline' src/app/globals.css && grep -q '\.dark {' src/app/globals.css && grep -q -- '--focus-ring' src/app/globals.css</verify>
  <done>globals.css has @theme inline color indirection, a .dark palette, a class dark variant, and a var-driven focus ring; light values unchanged.</done>
</task>
```

### Task 2.1 — ThemeToggle component + i18n + mount in header (wave 2)

```xml
<task id="2.1" wave="2">
  <files>apps/web/src/components/theme/ThemeToggle.tsx, apps/web/messages/en.json, apps/web/messages/vi.json, apps/web/src/components/app-shell/AppShell.tsx</files>
  <action>
Create `apps/web/src/components/theme/ThemeToggle.tsx` (client component, mirrors LocaleSwitcher styling — pill border, token colors, inline SVG, no lucide):
- Use `useTheme()` from next-themes and `useTranslations("ThemeToggle")`.
- Guard against hydration mismatch: track a `mounted` flag (`useEffect(() => setMounted(true), [])`); before mount, render a non-interactive placeholder of the same size to avoid layout shift.
- Toggle between `"light"` and `"dark"` on click (`resolvedTheme === "dark" ? setTheme("light") : setTheme("dark")`).
- Render an inline sun SVG in dark mode (action: go light) and an inline moon SVG in light mode. `aria-label` = `t("toggle")`; `aria-pressed` reflects dark state.
- Style: `rounded-pill border border-line bg-panel-raised text-ink hover:border-ink hover:bg-panel` + focus uses the global neutral ring (do NOT add a custom ring).

Add i18n keys under a new `"ThemeToggle"` namespace in BOTH `messages/en.json` and `messages/vi.json`:
- en: `{ "toggle": "Toggle theme", "light": "Light", "dark": "Dark" }`
- vi: `{ "toggle": "Đổi giao diện", "light": "Sáng", "dark": "Tối" }`

Mount `<ThemeToggle />` in `AppShell.tsx`'s right-hand cluster `<div className="ml-auto flex items-center gap-sm">`, placed BEFORE `<UserMenu />` and after the `LocaleSwitcher` wrapper (keep it visible on mobile too — do not wrap in the `hidden sm:block` used for LocaleSwitcher).
  </action>
  <verify>cd apps/web && pnpm exec tsc --noEmit && pnpm lint</verify>
  <done>ThemeToggle compiles, is mounted in the header, has en+vi strings, and lints clean.</done>
</task>
```

### Task 2.2 — Hardcoded-color sweep: chat surfaces (wave 2)

```xml
<task id="2.2" wave="2">
  <files>apps/web/src/components/chat/ChatPanel.tsx, apps/web/src/components/chat/ChatHeader.tsx, apps/web/src/components/chat/ChatComposer.tsx, apps/web/src/components/chat/ChatEmptyState.tsx, apps/web/src/components/chat/MessageList.tsx, apps/web/src/components/chat/InterruptPrompt.tsx</files>
  <action>
Replace hardcoded colors with semantic tokens so the chatbot flips in dark mode. For each file, convert: `bg-white` → `bg-panel`; `text-white` on accent/ink fills → `text-on-accent`; `text-black` → `text-ink`; `bg-black`/`#000`/`#fff` and arbitrary hex (`bg-[#xxxxxx]`) → the nearest existing token (`bg-panel`, `bg-panel-raised`, `bg-void`, `border-line`, `text-muted`, etc.).

Specific known fixes:
- `ChatPanel.tsx:43` `bg-white` → `bg-panel`.
- `ChatPanel.tsx:72` `bg-surface` is an UNDEFINED token (no `--color-surface` exists) — this is a pre-existing bug (Rule 1 auto-fix). Replace with `bg-panel-raised`. Record in SUMMARY `### Deviations`.
- Audit each file with `grep -nE "text-white|text-black|bg-white|bg-black|#fff|#000|#[0-9a-fA-F]{3,6}|bg-\[#"` and convert every hit to a token. Streamdown markdown styles flow from `AssistantMarkdown` + the `@source` scan and inherit tokens — do not touch streamdown internals.

Preserve all non-color classes, spacing, and behavior. Do not restructure components.
  </action>
  <verify>cd apps/web && pnpm exec tsc --noEmit && pnpm test -- src/components/chat</verify>
  <done>No hardcoded light-only colors remain in the six chat files; MessageList tests pass; the bg-surface bug is fixed.</done>
</task>
```

### Task 2.3 — Hardcoded-color sweep: app surfaces (wave 2)

```xml
<task id="2.3" wave="2">
  <files>apps/web/src/components/auth/UserMenu.tsx, apps/web/src/components/ui/Button.tsx, apps/web/src/app/trips/[tripId]/page.tsx, apps/web/src/components/trips/tripVisuals.tsx</files>
  <action>
Same token-conversion sweep as Task 2.2, for the app-surface files.

Specific known fixes:
- `Button.tsx:23` primary variant `"bg-ink text-white hover:bg-[#2e2e2e]"` → `"bg-ink text-on-accent hover:bg-ink-hover"`. Rationale: in dark mode `bg-ink` flips to light, so `text-white` becomes unreadable; `text-on-accent` is the correct on-fill token (dark in both themes), and `--ink-hover` (added in Task 1.2) replaces the hardcoded hover hex. If `bg-ink-hover` is not yet picking up the token, use `hover:bg-[var(--ink-hover)]`.
- Audit each file with the same grep as Task 2.2 and convert every hardcoded color to a token. `tripVisuals.tsx` may legitimately map data → topic/status tokens; keep those token references (they now flip via Task 1.2) and only convert raw `#hex`/`text-white`-style literals.

Preserve all non-color classes and behavior.
  </action>
  <verify>cd apps/web && pnpm exec tsc --noEmit && pnpm test -- src/components/ui</verify>
  <done>No hardcoded light-only colors remain in the four files; primary Button is readable in both themes; Button tests pass.</done>
</task>
```

### Task 3.1 — Playwright theme e2e + full verify (wave 3)

```xml
<task id="3.1" wave="3">
  <files>apps/web/playwright/theme.spec.ts</files>
  <action>
Create `apps/web/playwright/theme.spec.ts` (mirror `playwright/trip-smoke.spec.ts` setup) proving:
1. Default-system: with `colorScheme: "dark"` context, `<html>` carries class `dark` on first load; with `colorScheme: "light"`, it does not.
2. Toggle: clicking the header theme toggle (locate by `aria-label` from the `ThemeToggle.toggle` string) adds/removes `dark` on `<html>` and writes `localStorage.theme`.
3. Persistence: after `page.reload()`, the toggled theme is retained.
4. No-FOUC smoke: assert `<html>` already has the resolved class before the first paint hook (e.g. read class immediately after `goto` with `waitUntil: "commit"`).

Run the full verification sweep and record results in SUMMARY `### Verify`.
  </action>
  <verify>cd apps/web && pnpm exec tsc --noEmit && pnpm lint && pnpm test && pnpm e2e -g "theme"</verify>
  <done>Theme e2e passes (default-by-OS, toggle, persistence, no-FOUC); typecheck, lint, and unit tests green.</done>
</task>
```

## 5. Risks

- **TW v4 `@theme inline` indirection** is the load-bearing change — if a flipping token is left in a plain `@theme` block, it won't switch. Mitigation: Task 1.2 verify greps for the structure; Task 3.1 e2e proves visual flip.
- **FOUC**: next-themes injects a pre-paint script; `suppressHydrationWarning` on `<html>` (Task 1.1) is mandatory or React logs hydration errors. Covered by Task 3.1 #4.
- **Playwright in CI/headless** may need the dev server (`playwright.config.ts` webServer) and Node v24; e2e is the only >instant check. Unit/typecheck/lint remain the fast gates.
- **Dark palette contrast** is hand-tuned, not formally measured. If any status/topic color fails AA on dark, adjust the single hex in `.dark` (isolated, reversible).

## 6. Wave / Parallelism

| Wave | Tasks | Parallelism | Files disjoint? |
|------|-------|-------------|-----------------|
| 1 | 1.1 provider+layout, 1.2 token refactor | 2 parallel | ✅ (package.json/ThemeProvider/layout vs globals.css) |
| 2 | 2.1 toggle+i18n, 2.2 chat sweep, 2.3 app sweep | 3 parallel | ✅ (theme+AppShell vs chat/* vs ui+auth+trips) |
| 3 | 3.1 e2e + full verify | single | — |

## 7. Status Log

- 2026-06-27 — Plan drafted on `feat/light-dark-mode` (off `v3`). Status: active.
- 2026-06-28 — Executed via subagent-driven-development. Commits scattered across branches by concurrent activity in the shared checkout; recovered by rebuilding a clean branch `feat/light-dark-mode-clean` off `v3` in an isolated worktree (`.claude/worktrees/light-dark-mode`) and cherry-picking. All tasks done + reviewed.
  - Wave 1: `6a92f19` (1.1), `5da9aa3` (1.2), `8d3e4a3` (color-scheme review fix).
  - Wave 2: `82be8f2` (on-ink token), `f510cd0` (2.1), `35ba0c0` (2.2), `e7a790f` (2.3), `da31d28` (lime-contrast + ink-hover review fixes).
  - Wave 3: `d309d9a` (3.1 e2e).
  - Final correctness + intent review → `3e51e50` (completed sweep on plan-omitted surfaces + hardened FOUC test).
  - Verify: tsc 0, lint 0, theme e2e 5/5; unit 50/52 (2 pre-existing unrelated failures). Status: shipped (PR pending).
