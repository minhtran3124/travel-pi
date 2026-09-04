import { loadEnvConfig } from "@next/env";
import { defineConfig, devices } from "@playwright/test";
import { STORAGE_STATE } from "./playwright/e2e-env";

/**
 * Playwright e2e config — opt-in, NOT part of the fast CI path.
 *
 * The fast unit runner is vitest (`pnpm test`), scoped to `src/`. These e2e
 * specs live in `./playwright` and run only via `pnpm e2e`.
 *
 * Two projects run in a graph:
 *   - `setup` — matches `*.setup.ts`, authenticates once and writes the
 *     storage state consumed below.
 *   - `chromium` — the actual specs; depends on `setup` and loads its saved
 *     `storageState` so every spec starts already signed in.
 *
 * `loadEnvConfig` (from `@next/env`, resolved against THIS file's directory
 * via `__dirname`, not `process.cwd()`) pulls a local `.env.local` into the
 * runner process the same way `next dev` does; it never overrides an
 * already-set variable, so CI's exported secrets still win.
 *
 * Assumes the FastAPI backend is started separately on :8000 (see the spec
 * file header for the full run recipe). The `webServer` block boots the Next
 * dev server on :3000 and reuses an already-running one when present.
 */
loadEnvConfig(__dirname);

export default defineConfig({
  testDir: "./playwright",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    { name: "setup", testMatch: /.*\.setup\.ts/ },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], storageState: STORAGE_STATE },
      dependencies: ["setup"],
    },
  ],
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    // First Next compile can be slow; give it room.
    timeout: 120_000,
  },
});
