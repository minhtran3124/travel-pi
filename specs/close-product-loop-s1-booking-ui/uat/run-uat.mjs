/**
 * Browser UAT for the S1 booking slice — one screenshot per case.
 *
 * Playwright's MCP server is broken in this environment (URL.canParse), so this
 * drives playwright-core directly under Node 24, the pattern the repo already
 * uses for UI verification.
 *
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   cd apps/web && node ../../specs/close-product-loop-s1-booking-ui/uat/run-uat.mjs
 *
 * Requires: the web dev server on BASE (default :3001) and the API on :8000,
 * plus E2E_USER_EMAIL / E2E_USER_PASSWORD in apps/web/.env.local.
 *
 * Case 3 depends on the signed-in account's tier. On a free account it captures
 * the upgrade dialog; on a premium one it captures the confirmed booking and
 * the trip's Bookings tab. The script reports which branch it took.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

// This file lives under specs/, so bare-specifier resolution would look for
// node_modules next to it. playwright-core is a transitive dependency of
// @playwright/test, so pnpm keeps it in the store rather than hoisting it;
// resolve it from @playwright/test, which apps/web depends on directly.
const require = createRequire(new URL("../../../apps/web/package.json", import.meta.url));
const playwrightTestEntry = require.resolve("@playwright/test");
const requireFromTest = createRequire(playwrightTestEntry);
const { chromium } = requireFromTest("playwright-core");

const BASE = process.env.UAT_BASE ?? "http://localhost:3001";
const OUT = new URL("./", import.meta.url).pathname;

function envFromLocal(key) {
  if (process.env[key]) return process.env[key];
  const raw = readFileSync(new URL("../../../apps/web/.env.local", import.meta.url), "utf8");
  const line = raw.split("\n").find((l) => l.startsWith(`${key}=`));
  return line?.slice(key.length + 1).trim().replace(/^["']|["']$/g, "");
}

const EMAIL = envFromLocal("E2E_USER_EMAIL");
const PASSWORD = envFromLocal("E2E_USER_PASSWORD");
if (!EMAIL || !PASSWORD) throw new Error("E2E_USER_EMAIL / E2E_USER_PASSWORD not found");

const stamp = Date.now();
const passengerName = `UAT Passenger ${stamp}`;
const results = [];

async function shot(page, name, note) {
  await page.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
  results.push({ name, note });
  console.log(`  captured ${name}.png — ${note}`);
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
page.setDefaultTimeout(20_000);

// Surface why a booking failed instead of leaving a bare locator timeout.
page.on("console", (m) => {
  if (m.type() === "error") console.log("  [console]", m.text().slice(0, 200));
});
page.on("response", async (r) => {
  if (r.url().includes("/book") && r.status() >= 400) {
    console.log(`  [http ${r.status()}]`, (await r.text().catch(() => "")).slice(0, 300));
  }
});

try {
  // --- Sign in ---------------------------------------------------------------
  await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', EMAIL);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.startsWith("/auth/login"), { timeout: 30_000 });
  console.log("signed in as", EMAIL);

  // --- Case 1: the two new nav entries ---------------------------------------
  await page.goto(`${BASE}/trips`, { waitUntil: "networkidle" });
  await shot(page, "01-nav-flights-hotels", "Flights and Hotels appear in the app nav");

  // --- Create a trip the booking can attach to -------------------------------
  await page.getByRole("button", { name: "New trip" }).first().click();
  const tripTitle = `UAT Booking Trip ${stamp}`;
  await page.getByLabel("Trip name").fill(tripTitle);
  await page.getByRole("button", { name: "Create trip" }).click();
  await page.waitForURL(/\/trips\/[^/]+$/);
  const tripId = page.url().split("/trips/")[1];
  console.log("trip", tripId);

  // --- Case 2: flight search results ------------------------------------------
  await page.goto(`${BASE}/flights?tripId=${tripId}`, { waitUntil: "networkidle" });
  await page.getByLabel("Origin").fill("DAD");
  await page.getByLabel("Destination").fill("SGN");
  const departureDate = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
  await page.getByLabel("Departure date").fill(departureDate);
  await page.getByRole("button", { name: "Search flights" }).click();
  await page.getByRole("button", { name: "Book" }).first().waitFor();
  await shot(page, "02-flights-search-results", "DAD to SGN search returns bookable fares");

  // --- Case 3: the booking dialog, one-seat notice and trip select ------------
  await page.getByRole("button", { name: "Book" }).first().click();
  await page.getByRole("dialog", { name: "Book flight" }).waitFor();
  await page.getByLabel("Traveller name").fill(passengerName);
  await page.getByLabel("Email").fill(`uat-${stamp}@example.com`);
  await page.getByLabel("Phone").fill("0900000000");
  await shot(
    page,
    "03-flight-book-dialog",
    "book dialog: one-seat notice and the trip preselected from ?tripId=",
  );

  // --- Case 4: whichever outcome this account's tier produces -----------------
  await page.getByRole("button", { name: "Confirm booking" }).click();
  const upgrade = page.getByRole("dialog", { name: "Upgrade required" });
  const success = page.getByRole("dialog", { name: "Booking confirmed" });
  await upgrade.or(success).waitFor();

  let tier;
  if (await upgrade.isVisible()) {
    tier = "free";
    await shot(page, "04-free-tier-upgrade-dialog", "free account: the 403 opens the upgrade dialog");
    await page.getByRole("button", { name: "Got it" }).click();
  } else {
    tier = "premium";
    await shot(page, "04-premium-booking-confirmed", "premium account: the booking is confirmed");
  }
  console.log("tier branch:", tier);

  // --- Case 5: the trip's Bookings tab ---------------------------------------
  await page.goto(`${BASE}/trips/${tripId}`, { waitUntil: "networkidle" });
  await page.getByRole("tab", { name: "Bookings" }).click();
  await page.waitForTimeout(1500);
  await shot(
    page,
    "05-trip-bookings-tab",
    tier === "premium"
      ? "the booking is listed against this trip"
      : "empty for a free account, since nothing was booked",
  );

  // --- Case 6: the two budget totals, labelled -------------------------------
  await page.getByRole("tab", { name: "Budget" }).click();
  await page.waitForTimeout(1500);
  await shot(page, "06-trip-budget-two-totals", "budget shows booked-for-this-trip beside itinerary spend");

  // --- Case 7: hotel search results ------------------------------------------
  await page.goto(`${BASE}/hotels?tripId=${tripId}`, { waitUntil: "networkidle" });
  await page.getByLabel("City").fill("Da Nang");
  await page.getByLabel("Check-in").fill(departureDate);
  const checkOut = new Date(Date.now() + 32 * 864e5).toISOString().slice(0, 10);
  await page.getByLabel("Check-out").fill(checkOut);
  await page.getByRole("button", { name: "Search hotels" }).click();
  await page.getByRole("button", { name: "Book" }).first().waitFor();
  await shot(page, "07-hotels-search-results", "Da Nang availability for the chosen dates");

  // --- Case 8: the hotel booking dialog --------------------------------------
  await page.getByRole("button", { name: "Book" }).first().click();
  await page.getByRole("dialog", { name: "Book hotel" }).waitFor();
  await shot(page, "08-hotel-book-dialog", "hotel book dialog with the trip preselected");

  console.log(`\n${results.length} screenshots written to ${OUT}`);
  console.log(`tier: ${tier}`);
} catch (err) {
  await page.screenshot({ path: `${OUT}zz-failure.png`, fullPage: true }).catch(() => {});
  const dialog = await page
    .getByRole("dialog")
    .first()
    .innerText()
    .catch(() => "(no dialog on screen)");
  console.log("\nFAILED — dialog text was:\n", dialog.slice(0, 500));
  throw err;
} finally {
  await browser.close();
}
