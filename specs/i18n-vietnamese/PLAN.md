---
slug: i18n-vietnamese
status: shipped
owner: Minh Tran
created: 2026-06-26
---

# Multi-language UI (Vietnamese first)

## 1. Motivation

Make the web app (`apps/web/`) speak more than one language, starting with
**Vietnamese alongside English**. A user can flip a switcher in the app shell and the
entire UI — navigation, trip/place/booking screens, and the **chatbot's UI shell**
(placeholder, empty-state greeting, suggestion chips, header, error states) — re-renders in
the chosen language. The locale is remembered across reloads via a cookie; **no URL changes**.

Built on **next-intl** in "App Router without i18n routing" mode (cookie-driven locale).

## 2. Non-goals

- **The AI agent's reply content is NOT translated.** We touch only the chat *UI shell*, never
  the streamed assistant message text. No changes to `apps/api/` — no `ChatRequest.language`
  field, no `TravelAgentState`, no prompt files. This is a **frontend-only** change.
  (Note: `SupervisorIntent.language` exists in the backend but stays out of scope here.)
- No locale in the URL (no `/vi/...` subpaths). Cookie-based only.
- No automatic browser-language detection on first visit (default = `en`). Can be added later.
- No third/fourth languages yet — the scaffolding is built to scale, but only `en` + `vi` ship.
- No translation-management tooling (Crowdin/Lokalise). Catalogs are plain JSON in-repo.

## 3. Success Criteria

1. A locale switcher in the app shell toggles `en ⇄ vi`; selection persists across reloads.
2. All currently-hardcoded UI copy renders from message catalogs; nothing visible is hardcoded English when `vi` is active (excluding agent reply content, by design).
3. Dates and currency render with locale-appropriate formatting (`en-US` vs `vi-VN`) via next-intl's formatter.
4. `<html lang>` reflects the active locale.
5. `pnpm --filter web exec tsc --noEmit` and `pnpm --filter web lint` pass; `pnpm --filter web build` succeeds.
6. `vi.json` is a complete, reviewable draft translation (every key in `en.json` has a Vietnamese value).

## 4. Tasks

> Run all FE commands with Node v24: `export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"`.
> Reminder: `max-w-{sm,md,lg}` are broken in this repo's TW v4 — irrelevant here but don't add them.

### Task 1.1 — Install next-intl + wire the Next.js plugin

```xml
<task id="1.1" wave="1">
  <files>apps/web/package.json, apps/web/next.config.ts, pnpm-lock.yaml</files>
  <action>Add next-intl (latest) to apps/web deps via pnpm (Node v24). Wrap the Next config with createNextIntlPlugin('./src/i18n/request.ts'). Do not change any other config options.</action>
  <verify>cd apps/web && pnpm --filter web exec tsc --noEmit</verify>
  <done>next-intl resolves; config compiles; lockfile updated.</done>
</task>
```

### Task 1.2 — i18n config, request handler, and cookie locale actions

```xml
<task id="1.2" wave="1">
  <files>apps/web/src/i18n/config.ts, apps/web/src/i18n/request.ts, apps/web/src/i18n/locale.ts</files>
  <action>config.ts: export `locales = ['en','vi'] as const`, `type Locale`, `defaultLocale = 'en'`, `LOCALE_COOKIE = 'locale'`. request.ts: getRequestConfig reads the cookie (fallback defaultLocale), validates against locales, dynamically imports `../../messages/${locale}.json`, and exposes shared `formats` presets (short/long date, USD currency). locale.ts ('use server'): `getUserLocale()` reads cookie; `setUserLocale(locale)` writes the cookie (1yr, path '/'). Use core-strings only — no UI here.</action>
  <verify>cd apps/web && pnpm --filter web exec tsc --noEmit</verify>
  <done>getRequestConfig returns a valid locale + messages; server actions read/write the cookie.</done>
</task>
```

### Task 2.1 — Author the English catalog (source of truth)

```xml
<task id="2.1" wave="2">
  <files>apps/web/messages/en.json</files>
  <action>Sweep apps/web/src for hardcoded user-facing strings and centralize them into a namespaced en.json (suggested namespaces: Nav, Trips, TripDetail, Budget, Expenses, Itinerary, Shortlist, Places, Bookings, Chat, Common, Errors, LocaleSwitcher). Use ICU syntax for plurals/interpolation (trip counts, names, "have a great trip"). Keys are stable identifiers; values are the exact current English copy. This file is the contract every wave-3 task keys against.</action>
  <verify>cd apps/web && node -e "JSON.parse(require('fs').readFileSync('messages/en.json','utf8'))"</verify>
  <done>en.json is valid JSON and covers every string inventoried in waves below.</done>
</task>
```

### Task 2.2 — Provider in root layout + locale-aware `<html lang>`

```xml
<task id="2.2" wave="2">
  <files>apps/web/src/app/layout.tsx</files>
  <action>Make RootLayout async: `const locale = await getLocale()`. Set `<html lang={locale}>`. Wrap the existing provider tree (IdentityProvider/QueryProvider/AppShell/ChatWidget) with `<NextIntlClientProvider>`. Localize the exported metadata title/description via getTranslations('Common'). Do not reorder the existing providers.</action>
  <verify>cd apps/web && pnpm --filter web exec tsc --noEmit</verify>
  <done>App renders under NextIntlClientProvider; html lang reflects the cookie locale.</done>
</task>
```

### Task 2.3 — Locale switcher in the app shell

```xml
<task id="2.3" wave="2">
  <files>apps/web/src/components/app-shell/LocaleSwitcher.tsx, apps/web/src/components/app-shell/AppShell.tsx</files>
  <action>Build a small LocaleSwitcher: a client component reading useLocale(), rendering en/vi options, calling setUserLocale() in a useTransition then router.refresh() to re-render server components. Mount it in AppShell's header/nav. Keep it styled consistently with existing shell controls (ink/lime tokens). Only AppShell's own copy is migrated here if trivially adjacent; full nav-label migration is Task 3.1.</action>
  <verify>cd apps/web && pnpm --filter web exec tsc --noEmit</verify>
  <done>Switcher toggles locale, persists via cookie, and refreshes the tree.</done>
</task>
```

### Task 3.1 — Migrate app-shell + global pages (parallel-safe)

```xml
<task id="3.1" wave="3">
  <files>apps/web/src/components/app-shell/AppShell.tsx, apps/web/src/app/error.tsx, apps/web/src/app/not-found.tsx, apps/web/src/app/page.tsx</files>
  <action>Replace hardcoded copy (nav labels "Trips/Places/Bookings", "Travel Planner", error/not-found text) with useTranslations('Nav'|'Errors'|'Common') keys from en.json. No behavior changes.</action>
  <verify>cd apps/web && pnpm --filter web exec tsc --noEmit && pnpm --filter web lint</verify>
  <done>Zero hardcoded user copy remains in these files.</done>
</task>
```

### Task 3.2 — Migrate the chat UI shell (parallel-safe; agent content untouched)

```xml
<task id="3.2" wave="3">
  <files>apps/web/src/components/chat/ChatEmptyState.tsx, apps/web/src/components/chat/ChatComposer.tsx, apps/web/src/components/chat/ChatHeader.tsx, apps/web/src/components/chat/ChatPanel.tsx, apps/web/src/components/chat/MessageList.tsx, apps/web/src/components/chat/InterruptPrompt.tsx, apps/web/src/components/chat/ChatLauncher.tsx</files>
  <action>Replace shell copy (greeting, 4 suggestion labels+prompts, "Try asking", composer placeholder + aria-labels, header text, empty/loading/error states, interrupt prompts, launcher label) with useTranslations('Chat') keys. CRITICAL: do NOT touch rendered assistant/user message *content* in MessageList — only its surrounding chrome (timestamps, status, empty/error labels).</action>
  <verify>cd apps/web && pnpm --filter web exec tsc --noEmit && pnpm --filter web lint</verify>
  <done>Chat shell is fully localized; streamed agent text is byte-for-byte unchanged.</done>
</task>
```

### Task 3.3 — Migrate Trips domain + localize its date/currency (parallel-safe)

```xml
<task id="3.3" wave="3">
  <files>apps/web/src/components/trips/TripCard.tsx, apps/web/src/components/trips/TripHeader.tsx, apps/web/src/components/trips/tripVisuals.tsx, apps/web/src/components/trips/budget/BudgetTab.tsx, apps/web/src/components/trips/expenses/ExpensesTab.tsx, apps/web/src/components/trips/itinerary/ItineraryTab.tsx, apps/web/src/components/trips/itinerary/ItemRow.tsx, apps/web/src/components/trips/shortlist/ShortlistTab.tsx, apps/web/src/app/trips/[tripId]/page.tsx</files>
  <action>Replace hardcoded copy with useTranslations('Trips'|'TripDetail'|'Budget'|'Expenses'|'Itinerary'|'Shortlist') keys. Replace `Intl.DateTimeFormat("en-US",...)` (tripVisuals.dateRange, ItineraryTab) and `toLocaleString("en-US",{currency})` (ExpensesTab.money) with next-intl's useFormatter()/getFormatter() so they follow the active locale. Keep the existing date/money output shape for `en`.</action>
  <verify>cd apps/web && pnpm --filter web exec tsc --noEmit && pnpm --filter web lint</verify>
  <done>Trips screens localized; dates/currency render vi-VN under `vi`, identical under `en`.</done>
</task>
```

### Task 3.4 — Migrate Places + Bookings, incl. booking currency (parallel-safe)

```xml
<task id="3.4" wave="3">
  <files>apps/web/src/components/places, apps/web/src/components/bookings/BookingTable.tsx, apps/web/src/app/places, apps/web/src/app/bookings</files>
  <action>Replace hardcoded copy in places + bookings components/pages with useTranslations('Places'|'Bookings') keys. Swap BookingTable's `toLocaleString("en-US",{currency: booking.currency})` for next-intl useFormatter().number(...,{style:'currency'}) using the active locale. NewTripModal copy → Trips/Common keys if it lives here; otherwise leave to 3.3 (avoid file overlap).</action>
  <verify>cd apps/web && pnpm --filter web exec tsc --noEmit && pnpm --filter web lint</verify>
  <done>Places + Bookings localized; booking amounts format per active locale.</done>
</task>
```

### Task 4.1 — Draft the Vietnamese catalog

```xml
<task id="4.1" wave="4">
  <files>apps/web/messages/vi.json</files>
  <action>Produce a complete Vietnamese translation: every key present in en.json (final, post-wave-3) gets a natural Vietnamese value, preserving ICU placeholders and plural categories. Travel-domain tone, not literal MT. Flag any uncertain phrasing in the PR description for human review.</action>
  <verify>cd apps/web && node -e "const a=require('./messages/en.json'),b=require('./messages/vi.json');const f=(o,p='')=>Object.entries(o).flatMap(([k,v])=>typeof v==='object'?f(v,p+k+'.'):[p+k]);const ea=f(a),eb=new Set(f(b));const miss=ea.filter(k=>!eb.has(k));if(miss.length){console.error('Missing vi keys:',miss);process.exit(1)}console.log('vi.json complete:',ea.length,'keys')"</verify>
  <done>vi.json key-set equals en.json key-set; no missing keys.</done>
</task>
```

### Task 5.1 — End-to-end acceptance

```xml
<task id="5.1" wave="5">
  <files>apps/web</files>
  <action>Run a production build and a manual smoke: load the app, toggle the switcher to vi, reload, confirm persistence; verify chat shell, trips dates/currency, nav, and error pages all render Vietnamese while streamed agent replies are unaffected. Verify UI via the Node24 + playwright-core script (Playwright MCP is broken in this repo) against localhost:3000.</action>
  <verify>cd apps/web && pnpm --filter web build</verify>
  <done>Build passes; vi/en toggle works and persists; agent reply content unchanged.</done>
</task>
```

## 5. Risks

- **String inventory completeness** — a missed hardcoded string silently stays English under `vi`. Mitigation: wave-3 tasks each assert "zero hardcoded copy remains in their files"; a grep sweep for JSX text literals during 2.1 seeds the catalog.
- **Server-component re-render on switch** — cookie-based switching needs `router.refresh()` after `setUserLocale()` so RSC subtree re-renders. Covered in 2.3; verify in 5.1.
- **ICU plural rules differ** — Vietnamese has no plural inflection (one form); ensure en's plural ICU still collapses correctly for vi values.
- **Hydration** — locale is server-resolved from the cookie, so no client/server mismatch (mirrors the existing IdentityProvider SSR-safe pattern). Avoid reading the cookie client-side for initial render.
- **Currency semantics** — formatting locale changes grouping/symbol placement, NOT the currency itself (USD stays USD); confirm we never accidentally convert amounts.

## 6. Status Log

- 2026-06-26 — Plan drafted. Scope locked: FE-only, cookie-based (no URL change), Vietnamese drafted in-repo, **agent reply content explicitly out of scope** (chat UI shell only). next-intl "without i18n routing" mode confirmed against current docs.
- 2026-06-26 — **Shipped.** All 5 waves complete. next-intl@4 installed + plugin wired; `i18n/{config,request,locale}.ts`; provider + locale-aware `<html lang>` in layout; `LocaleSwitcher` in app shell; ~25 component files migrated to `en.json` keys (356 keys); `vi.json` full draft (356 keys, parity verified). Date/currency now locale-aware via next-intl `useFormatter` (replaced all hardcoded `en-US`). Verify: `tsc --noEmit` ✅, `eslint src` ✅, `next build` ✅. Playwright smoke ✅ — en⇄vi toggle, cookie persistence across reload, chat shell + dates localized. Wave-3 ran as 5 parallel subagents over disjoint file sets.
  - **Known minor follow-ups** (cosmetic, non-blocking): (1) `TripDetail.gaps.blankCanvas` lost its bold "Itinerary" emphasis (next-intl v4 rich-text would restore it); (2) Shortlist `entry.source` pill ("catalog"/"saved") left as raw data — no catalog key; (3) all routes now `ƒ` dynamic (inherent to cookie-based locale).
  - **Needs human review:** `vi.json` phrasing — see PR notes for ~9 flagged strings (e.g. `whereToNext`, chat "co-pilot", `gaps.blankCanvas`).
