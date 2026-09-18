---
type: concept
title: Internationalization and theming
description: How the web app localizes and themes itself — cookie-based next-intl locale resolution without URL routing, the en/vi message catalogs and the tests that keep them in parity with each other and with the backend's supported languages, how the UI locale differs from the agent's detected reply language and the side-panel language, dark mode via next-themes with a class-based Tailwind variant, and the design-token system whose colors flip between themes through CSS-variable indirection.
tags: [i18n, next-intl, locale, theming, dark-mode, tailwind, design-tokens, frontend]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-04db353a082c76c88c1af099
    resource: repo://apps/api/app/core/languages.py
  - id: openwiki-source-4100b7e4a12b5efe146f7d16
    resource: repo://apps/api/tests/core/test_languages.py
  - id: openwiki-source-666959b6fb5f2c271023d583
    resource: repo://apps/web/playwright/theme.spec.ts
  - id: openwiki-source-52389a633001e0df1ac96558
    resource: repo://apps/web/src/app/globals.css
  - id: openwiki-source-af76d1604573613df875eba2
    resource: repo://apps/web/src/components/app-shell/LocaleSwitcher.tsx
  - id: openwiki-source-69679c129d6bc85862830eed
    resource: repo://apps/web/src/components/chat/panel/PanelIntlProvider.tsx
  - id: openwiki-source-fa5fa120ce1e7d6ce8573ad7
    resource: repo://apps/web/src/components/theme/ThemeProvider.tsx
  - id: openwiki-source-b16817c1135766bb464da2be
    resource: repo://apps/web/src/components/theme/ThemeToggle.tsx
  - id: openwiki-source-088486d3e09a4433cd1d83b6
    resource: repo://apps/web/src/i18n/config.ts
  - id: openwiki-source-65406f3820fc045882eb5350
    resource: repo://apps/web/src/i18n/locale.ts
  - id: openwiki-source-7da0aff454ab3a92186e40fb
    resource: repo://apps/web/src/i18n/request.ts
  - id: openwiki-source-075385f88afaea3b08054660
    resource: repo://apps/web/src/messages.parity.test.ts
  - id: openwiki-source-ca9eabc24825e6ff0edc2967
    resource: repo://DESIGN.md
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Internationalization and theming

Two cross-cutting concerns run through every page of `apps/web`: which language the interface speaks, and which theme it paints. Both are decided per request, both survive reloads, and both are deliberately decoupled from the language the **agent** replies in.

## Locale: cookie-based, no URL segment

`src/i18n/config.ts` declares the supported locales (`en`, `vi`), the default (`en`) and the `locale` cookie name; there is **no `[locale]` route segment**. `src/i18n/request.ts` is the `next-intl` request config: on every request it reads the cookie, falls back to the default, loads `messages/<locale>.json` and returns shared formatting presets (`short`/`long` dates, a `usd` currency style) so components using `useFormatter()` follow the active locale automatically. Because the cookie is read per request, routes are dynamic rather than statically generated, which is expected here. The root layout uses the same resolution for `<html lang>` and translated metadata.

The `LocaleSwitcher` in the app shell is a `<select>` that calls the `setUserLocale` server action (`src/i18n/locale.ts`, a one-year `lax` cookie) inside a transition and then `router.refresh()` so the server tree re-renders in the new locale. `NextIntlClientProvider` in the layout hands the catalog to client components, which call `useTranslations("<Namespace>")`.

## Message catalogs and parity

`apps/web/messages/en.json` and `vi.json` are organized by namespace (`Common`, `Nav`, `Trips`, `TripDetail`, `Budget`, `Expenses`, `Itinerary`, `Chat`, `Panel`, `Errors` and so on). Two tests keep the two sides of the system honest:

- `src/messages.parity.test.ts` flattens every leaf key path in both catalogs and fails if any key exists in one file but not the other, in either direction, listing the offenders.
- On the backend, `tests/core/test_languages.py` parses `export const locales = [...]` and `defaultLocale` out of the frontend config file and asserts they equal `SUPPORTED_LANGUAGES` and `DEFAULT_LANGUAGE` in `app/core/languages.py`, so the two language lists cannot drift (see [Agent state, runtime context and reply language](../agent/state-context-and-language.md)).

Follow-up suggestion chips and tool names in the activity trail are also resolved from the catalog: the backend sends locale-agnostic keys, and the client localizes them (see [Chat widget and streaming client](chat-and-streaming-client.md)).

## Three languages, on purpose

It is possible for a single screen to involve three language decisions, and they are kept separate deliberately:

1. **UI locale** (the cookie) drives navigation, forms, catalog pages and error copy.
2. **Agent reply language** is detected by the supervisor from the conversation itself and pinned on every model reply; the frontend never sends the UI locale to the agent. A Vietnamese traveller with an English UI still gets Vietnamese answers.
3. **Panel language** is the language the backend localized a side-panel payload to, streamed on `panel` and `done` events. The chat drawer wraps its subtree in a nested `NextIntlClientProvider` fed only the `Panel` slice of the matching catalog, so panel tab labels and static strings follow the conversation rather than the cookie.

Catalog text for hotels and places is localized on the backend through the content-translation store, not in the browser (see [Destinations, places and travel information](../domain/destinations-places-and-travel-info.md)).

## Theme: system default, class-based dark mode

`ThemeProvider` wraps `next-themes` with `attribute="class"`, `defaultTheme="system"`, `enableSystem` and `disableTransitionOnChange`, so the `dark` class lands on `<html>` before hydration (hence `suppressHydrationWarning` on the root element) and the initial theme follows the operating system; the Playwright theme spec checks both OS preferences. `globals.css` registers a Tailwind v4 `@custom-variant dark` scoped to `.dark`, so `dark:` utilities apply under that class.

`ThemeToggle` only renders after hydration: `next-themes` resolves the active theme on the client, so the toggle uses a `useSyncExternalStore`-based `useMounted` flag and shows a same-size, aria-hidden placeholder during server render and first paint to avoid both a hydration mismatch and layout shift. Once mounted it flips between `light` and `dark` with `aria-pressed` reflecting the state.

## Design tokens and the light/dark flip

`globals.css` implements the design system described in the repo-root `DESIGN.md` (the design source of truth for UI work). Tokens are split into two Tailwind v4 blocks:

- **`@theme inline`** declares every color and shadow token as an indirection to a bare CSS variable (`--color-panel: var(--panel)`, `--shadow-card: var(--shadow-card-v)`). The bare variables are defined once under `:root` (the canonical light palette, with `color-scheme: light`) and again under `.dark` (with `color-scheme: dark`, lifted panel surfaces, inverted `ink`, deeper shadows). Because Tailwind utilities reference the indirected token, `bg-panel` or `text-ink` flip automatically without duplicating utility classes.
- **`@theme`** declares the non-flipping tokens: the Inter and mono font stacks, radii (`sm` 10px, `md` 16px, `lg` 20px, `pill`), and named spacing steps (`xs` 4px through `xl` 24px).

Two paired tokens encode a rule that is easy to get wrong: `on-accent` is the text color on the lime accent (dark ink in both themes), while `on-ink` is the text color on an ink-filled primary action and **must invert** with the theme (white in light, near-black in dark) to stay readable. Semantic groups cover surfaces (`void`, `panel`, `panel-raised`, `line`, `line-soft`, `scrim`), text (`ink`, `ink-hover`, `muted`, `faint`), a status spectrum for bookings, a topic palette for tips, and the warm `coral` secondary accent that is decorative only.

The design rules the tokens enforce, from `DESIGN.md`: Departure Lime (`#cbf24a`) is the one brand accent and appears on at most 10 % of any screen, only for active, selected and highlight states; the primary action is always ink, never lime; focus rings use the global neutral `*:focus-visible` rule rather than the accent; native `window.confirm`/`alert`/`prompt` are never used (a `ConfirmDialog`/`Modal` primitive is); and every animation, including the chat panel's entrance, collapses under `prefers-reduced-motion`. `streamdown`'s bundled classes are added as a Tailwind `@source` so streamed assistant markdown is styled.
