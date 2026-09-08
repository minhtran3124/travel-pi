/**
 * Booking e2e smoke — create a trip, search flights, book one against that
 * trip, and assert it shows up on the trip's Bookings tab.
 *
 * Runs already signed in the same way `trip-smoke.spec.ts` does: the `setup`
 * project signs in once and saves the session, and the chromium project
 * reuses it via `storageState`, so this spec starts authenticated instead of
 * driving the login form.
 *
 * Booking is a premium-gated action (`require_premium` in
 * `app/routers/flights.py`). If the stored e2e credentials belong to a free
 * account, the book call 403s and the app opens the "Upgrade required"
 * dialog instead of the success view — that is asserted explicitly below and
 * fails with a clear message naming the cause, rather than timing out
 * waiting for a success state that will never appear.
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
 * (SQLite), so booking against a real trip is visible on that trip's page.
 */
import { expect, test } from "@playwright/test";

import { hasCreds } from "./e2e-env";

test.skip(!hasCreds, "E2E_USER_EMAIL/E2E_USER_PASSWORD not set");

test("search flight → book against a trip → appears on the trip's Bookings tab", async ({
  page,
}) => {
  const stamp = Date.now();
  const tripTitle = `E2E Booking Trip ${stamp}`;
  const passengerName = `E2E Passenger ${stamp}`;

  // --- Create a trip via the New-trip flow on /trips --------------------------
  await page.goto("/trips");

  await page.getByRole("button", { name: "New trip" }).first().click();

  const newTripDialog = page.getByRole("dialog", { name: "New trip" });
  await expect(newTripDialog).toBeVisible();
  await newTripDialog.getByLabel("Trip name").fill(tripTitle);
  await newTripDialog.getByRole("button", { name: "Create trip" }).click();

  await page.waitForURL(/\/trips\/[^/]+$/);
  await expect(
    page.getByRole("heading", { name: tripTitle }),
  ).toBeVisible();
  const tripId = page.url().split("/trips/")[1];

  // --- Search a flight, prefilled to attach the booking to this trip ---------
  await page.goto(`/flights?tripId=${tripId}`);

  await page.getByLabel("Origin").fill("DAD");
  await page.getByLabel("Destination").fill("SGN");
  const departureDate = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 10);
  await page.getByLabel("Departure date").fill(departureDate);
  await page.getByRole("button", { name: "Search flights" }).click();

  await expect(page.getByRole("button", { name: "Book" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Book" }).first().click();

  const bookDialog = page.getByRole("dialog", { name: "Book flight" });
  await expect(bookDialog).toBeVisible();
  await bookDialog.getByLabel("Traveller name").fill(passengerName);
  await bookDialog.getByLabel("Email").fill(`e2e-${stamp}@example.com`);
  await bookDialog.getByLabel("Phone").fill("0900000000");
  await bookDialog.getByRole("button", { name: "Confirm booking" }).click();

  // A free e2e account gets 403'd by `require_premium` and the app opens the
  // "Upgrade required" dialog instead of the success view — fail with a clear
  // cause instead of timing out on a success state that can't happen.
  const upgradeDialog = page.getByRole("dialog", { name: "Upgrade required" });
  const successDialog = page.getByRole("dialog", { name: "Booking confirmed" });
  await expect(upgradeDialog.or(successDialog)).toBeVisible();
  if (await upgradeDialog.isVisible()) {
    throw new Error(
      "Booking was rejected as premium-required (403) — E2E_USER_EMAIL must be a premium account for this spec to book.",
    );
  }

  // --- Assert the booking appears on the trip's Bookings tab -----------------
  await page.goto(`/trips/${tripId}`);
  await page.getByRole("tab", { name: "Bookings" }).click();
  await expect(page.getByText(passengerName)).toBeVisible();
});
