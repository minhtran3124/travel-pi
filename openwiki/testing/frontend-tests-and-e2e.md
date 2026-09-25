---
type: testing
title: Frontend unit tests and Playwright e2e
description: How the web app is tested — the Vitest and Testing Library unit runner with a load-bearing setup file that makes the relative-URL API client and the Supabase browser client work under Node, Mock Service Worker handlers registered per test, colocated component and hook tests, and the opt-in Playwright suite that signs in once through a setup project, reuses the saved session, loads credentials the same way next dev does, skips cleanly without secrets, and assumes a running backend.
tags: [testing, vitest, testing-library, msw, playwright, e2e, frontend]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-25T03:45:43.723Z
sources:
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-99de51df25f29bfc72caf823
    resource: repo://apps/web/package.json
  - id: openwiki-source-b718d27c389d0cfab47c5b2a
    resource: repo://apps/web/playwright.config.ts
  - id: openwiki-source-8cd55ac192a88e992cc5f401
    resource: repo://apps/web/playwright/auth.setup.ts
  - id: openwiki-source-280d6fbb33b44a877109b75a
    resource: repo://apps/web/playwright/booking-smoke.spec.ts
  - id: openwiki-source-baaaac5d829ee59fad4fa7c0
    resource: repo://apps/web/playwright/chat-feedback.spec.ts
  - id: openwiki-source-550f4b1ea6129c2723b0cc1b
    resource: repo://apps/web/playwright/e2e-env.ts
  - id: openwiki-source-9eb554d48c311fbf2b19069d
    resource: repo://apps/web/playwright/load-env.ts
  - id: openwiki-source-93cff9d2189b2348b2122cce
    resource: repo://apps/web/playwright/storage-state.ts
  - id: openwiki-source-3d755d7b6170f15c548e3e69
    resource: repo://apps/web/playwright/trip-smoke.spec.ts
  - id: openwiki-source-126a50005539743760628c6f
    resource: repo://apps/web/src/test/msw.ts
  - id: openwiki-source-ed86568d4fa73284b1c025c5
    resource: repo://apps/web/src/test/setup.ts
  - id: openwiki-source-6fe10cfb5ec054ca681eb262
    resource: repo://apps/web/vitest.config.ts
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Frontend unit tests and Playwright e2e

`apps/web` has two test layers with different scopes and costs: a fast Vitest suite that runs on every pull request, and a Playwright end-to-end suite that is opt-in locally and runs in CI only when the e2e secrets are configured.

## Unit and component tests (Vitest)

`vitest.config.ts` runs with the React plugin, a `jsdom` environment, globals enabled, the `@` alias mirrored from `tsconfig`, and an `include` scoped to `src/**/*.{test,spec}.{ts,tsx}` so the Playwright specs under `./playwright` are never collected. Tests are colocated next to their source (`ChatComposer.test.tsx`, `useAgentStream.stream.test.tsx`, `items.test.tsx`, `messages.parity.test.ts`). `pnpm test` runs `vitest run --passWithNoTests`; CI runs it between lint and build.

`src/test/setup.ts` is load-bearing and does three things in a deliberate order:

1. Sets dummy `NEXT_PUBLIC_SUPABASE_URL` and publishable-key values, because the Supabase browser client throws at construction without them and any component that mounts `useAgentStream` constructs one; the values are never dialed, since `getSession()` reads local storage and returns null.
2. Subclasses the global `Request` to absolutize relative string and URL inputs against the jsdom origin, because `openapi-fetch` builds `new Request("/api/be/...")` and undici rejects relative URLs.
3. Calls `server.listen({ onUnhandledRequest: "error" })` **at module top level**, not in `beforeAll`, because `openapi-fetch` captures `globalThis.fetch` when the client module is imported and MSW must patch fetch before that import; setup files finish before test modules load. Handlers reset after each test and the server closes after all.

`src/test/msw.ts` ships an intentionally empty base handler set; each test registers the endpoints it exercises with `server.use(http.get(`${BASE}/...`))` against `BASE = "/api/be"`. Hook tests wrap in a per-test `QueryClient` with `retry: false`, otherwise error-path tests hang on retries. Representative suites: the SSE parser and panel-key contract tests, the streaming hook's token, activity, panel, stop and hydration suites, the query hooks' full-replace, optimistic-rollback and typed-409 tests, the identity provider, `safeNextPath`, and the message-catalog parity test (see [Chat widget and streaming client](../frontend/chat-and-streaming-client.md), [Trips, bookings and catalog pages](../frontend/trips-bookings-and-catalog-pages.md) and [Internationalization and theming](../frontend/i18n-and-theming.md)).

## End-to-end tests (Playwright)

`playwright.config.ts` defines two projects that run as a graph: `setup`, matching `*.setup.ts`, signs in once and writes the browser session to a storage-state file, and `chromium` depends on it and loads that `storageState`, so every spec starts already authenticated instead of re-driving the login form. The `webServer` block boots `pnpm dev` on `:3000` (reusing a running server outside CI, with a generous first-compile timeout), `baseURL` is `http://localhost:3000`, traces are kept on first retry, and the `list` plus `html` reporters produce the `playwright-report/` directory that CI uploads on failure. The suite assumes the FastAPI backend is already running on `:8000`.

Credentials flow through two small modules. `playwright/load-env.ts` is imported **first** in the config and calls Next's own `loadEnvConfig` in dev mode, so `apps/web/.env.local` reaches the runner exactly as `next dev` reads it while already-exported CI secrets win. `playwright/e2e-env.ts` is the one module that reads `process.env` (`E2E_USER_EMAIL`, `E2E_USER_PASSWORD`, `hasCreds`); it avoids `import.meta` because Playwright transpiles it to CommonJS while Node's type stripping loads it as ESM. `playwright/storage-state.ts` anchors the storage-state path to its own directory, never `process.cwd()`, which is the documented cause of a setup project passing locally and failing on a CI runner.

Without both credentials the setup file **skips at file scope** (a body-level guard would still leave dependent specs pointing at a missing storage-state file), and every auth spec skips with it. The specs today:

- `trip-smoke.spec.ts` creates a trip, adds an itinerary item, reloads and asserts persistence.
- `booking-smoke.spec.ts` signs in, searches flights and asserts results render with **no booking control**, because booking now happens only through the chat assistant and the flights and hotels pages are browse-only.
- `theme.spec.ts` checks that the default theme follows the OS colour scheme in both directions.
- `chat-feedback.spec.ts` rates a reply and proves the rating survives reloads through every transition, then replays a request and probes another user's id. It is stricter than the others: it needs a backend with a **real LLM key**, because without one every chat turn takes the failure path whose fallback reply is unrateable by design, so it additionally requires `E2E_CHAT_LLM=1` and is skipped in CI, where the backend starts with every key blanked.

The CI e2e account is always **free tier**, so browser tests must not assume a premium outcome (see [Authentication and user tiers](../concepts/auth-and-tiers.md)).

## Running locally

```bash
# terminal 1, from apps/api
../../.venv/bin/uvicorn app.main:app --port 8000
# terminal 2, from apps/web (Node 24 on PATH)
pnpm exec playwright install chromium   # once
pnpm e2e                                # or: pnpm e2e --project=setup
```

Put `E2E_USER_EMAIL` and `E2E_USER_PASSWORD` for a confirmed Supabase account in `apps/web/.env.local`. The Playwright MCP integration is not reliable on the default Node 18; drive the browser from a Node 24 script instead. See [Local development, Docker and CI](../operations/local-dev-docker-and-ci.md) for the CI job that runs the same suite.
