import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e config — opt-in, NOT part of the fast CI path.
 *
 * The fast unit runner is vitest (`pnpm test`), scoped to `src/`. These e2e
 * specs live in `./playwright` and run only via `pnpm e2e`.
 *
 * Assumes the FastAPI backend is started separately on :8000 (see the spec
 * file header for the full run recipe). The `webServer` block boots the Next
 * dev server on :3000 and reuses an already-running one when present.
 */
export default defineConfig({
  testDir: "./playwright",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
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
