/**
 * Trip e2e smoke — create a trip, add an itinerary item, reload, assert persist.
 *
 * Runs already signed in: the `setup` project signs in once and saves the
 * session, and the chromium project reuses it via `storageState`, so this spec
 * starts authenticated instead of driving the login form.
 *
 * Opt-in / local only. NOT in the fast CI path (`pnpm test` = vitest, scoped to
 * src/). It still needs the FastAPI backend up on :8000, and the shared e2e
 * account's `E2E_USER_EMAIL` / `E2E_USER_PASSWORD` in `apps/web/.env.local`
 * (without both, the setup project and this spec are skipped — see the
 * file-scope guard below). Run it explicitly:
 *
 *   # from repo root — start the backend on :8000
 *   (cd apps/api && ../../.venv/bin/uvicorn app.main:app --port 8000)
 *
 *   # from apps/web — install the browser once, then run e2e
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   pnpm exec playwright install chromium
 *   pnpm e2e
 *
 * The dev server (:3000) is booted by playwright.config.ts (reused if already
 * running). The FE persists through the `/api/be/*` proxy → real BE (SQLite),
 * so a reload re-fetches from the backend and proves persistence.
 */
import { expect, test } from "@playwright/test";

import { hasCreds } from "./e2e-env";

test.skip(!hasCreds, "E2E_USER_EMAIL/E2E_USER_PASSWORD not set");

test("create trip → add itinerary item → persists across reload", async ({
  page,
}) => {
  const stamp = Date.now();
  const tripTitle = `E2E Trip ${stamp}`;
  const itemTitle = `E2E Item ${stamp}`;

  // --- Create a trip via the New-trip flow on /trips --------------------------
  await page.goto("/trips");

  await page.getByRole("button", { name: "New trip" }).first().click();

  const newTripDialog = page.getByRole("dialog", { name: "New trip" });
  await expect(newTripDialog).toBeVisible();
  await newTripDialog.getByLabel("Title").fill(tripTitle);
  await newTripDialog.getByRole("button", { name: "Create trip" }).click();

  // On success the app navigates to the trip detail page.
  await page.waitForURL(/\/trips\/[^/]+$/);
  await expect(
    page.getByRole("heading", { name: tripTitle }),
  ).toBeVisible();

  // --- Add an itinerary item (Itinerary tab is active by default) -------------
  await page.getByRole("button", { name: "Add item" }).first().click();

  const addItemDialog = page.getByRole("dialog", { name: "Add item" });
  await expect(addItemDialog).toBeVisible();
  await addItemDialog.getByLabel("Title").fill(itemTitle);
  await addItemDialog.getByRole("button", { name: "Save" }).click();

  // The item appears in the itinerary list.
  await expect(page.getByText(itemTitle)).toBeVisible();

  // --- Reload and assert the item persisted (re-fetched from the BE) ----------
  await page.reload();
  await expect(page.getByText(itemTitle)).toBeVisible();
});
