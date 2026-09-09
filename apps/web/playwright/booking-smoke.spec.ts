/**
 * Flights view-only smoke — sign in, search a flight, and assert results
 * render with no booking control on the page.
 *
 * Booking now happens exclusively through the chat assistant (product
 * decision, #close-product-loop-s1-booking-ui follow-up); `/flights` and
 * `/hotels` are browse-only. This spec used to book a flight against a trip
 * and assert the free/premium outcome — that path no longer exists.
 *
 * Runs already signed in the same way `trip-smoke.spec.ts` does: the `setup`
 * project signs in once and saves the session, and the chromium project
 * reuses it via `storageState`, so this spec starts authenticated instead of
 * driving the login form.
 *
 * Opt-in / local only. NOT in the fast CI path (`pnpm test` = vitest, scoped
 * to src/). It still needs the FastAPI backend up on :8000, and the shared
 * e2e account's `E2E_USER_EMAIL` / `E2E_USER_PASSWORD` in
 * `apps/web/.env.local` (without both, the setup project and this spec are
 * skipped — see the file-scope guard below). Run it explicitly:
 *
 *   # from repo root — start the backend on :8000
 *   (cd apps/api && ../../.venv/bin/uvicorn app.main:app --port 8000)
 *
 *   # from apps/web — install the browser once, then run e2e
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   pnpm exec playwright install chromium
 *   pnpm e2e
 *
 * The dev server (:3000) is booted by playwright.config.ts (reused if
 * already running). The FE persists through the `/api/be/*` proxy → real BE
 * (SQLite).
 */
import { expect, test } from "@playwright/test";

import { hasCreds } from "./e2e-env";

test.skip(!hasCreds, "E2E_USER_EMAIL/E2E_USER_PASSWORD not set");

test("search a flight and see results with no booking control", async ({
  page,
}) => {
  await page.goto("/flights");

  await page.getByLabel("Origin").fill("DAD");
  await page.getByLabel("Destination").fill("SGN");
  const departureDate = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 10);
  await page.getByLabel("Departure date").fill(departureDate);
  await page.getByRole("button", { name: "Search flights" }).click();

  await expect(
    page.getByText("Ask the assistant in chat to book this for you."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Book" })).toHaveCount(0);
});
