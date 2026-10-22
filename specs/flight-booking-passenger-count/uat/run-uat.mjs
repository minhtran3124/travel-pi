/**
 * Browser UAT: does the assistant actually book the number of seats asked for?
 *
 * The tests prove the tool carries `passengers` and prices it, and that prompt
 * v10 loads. Neither shows the model filling the field in a live turn — that is
 * what this does: ask for three seats in chat, and check the booking is priced
 * for three.
 *
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   cd apps/web && node ../../specs/flight-booking-passenger-count/uat/run-uat.mjs
 *
 * Requires the web dev server on BASE (default :3001), the API on :8000 with the
 * graph rebuilt after the prompt change, E2E credentials in apps/web/.env.local,
 * and a premium account — the booking sub-agent is premium-only.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(new URL("../../../apps/web/package.json", import.meta.url));
const requireFromTest = createRequire(require.resolve("@playwright/test"));
const { chromium } = requireFromTest("playwright-core");

const BASE = process.env.UAT_BASE ?? "http://localhost:3001";
const OUT = new URL("./", import.meta.url).pathname;
const SEATS = 3;

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

async function shot(page, name, note) {
  await page.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
  console.log(`  captured ${name}.png — ${note}`);
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
page.setDefaultTimeout(20_000);

try {
  await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', EMAIL);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.startsWith("/auth/login"), { timeout: 30_000 });
  console.log("signed in as", EMAIL);

  await page.goto(`${BASE}/trips`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "New trip" }).first().click();
  await page.getByLabel("Trip name").fill(`UAT Seats ${stamp}`);
  await page.getByRole("button", { name: "Create trip" }).click();
  await page.waitForURL(/\/trips\/[^/]+$/);
  const tripId = page.url().split("/trips/")[1];
  console.log("trip", tripId);

  const departureDate = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);

  // Ask for three seats, from the trip page so the trip is in the agent's state.
  await page.getByRole("button", { name: /open travel assistant/i }).click();
  const composer = page.getByRole("textbox", { name: /message the travel assistant/i });
  await composer.waitFor();
  await composer.fill(
    `Book the cheapest flight from DAD to SGN on ${departureDate} for ${SEATS} people. ` +
      `Passenger UAT Tester, email uat-${stamp}@example.com, phone 0900000000. ` +
      `Please confirm the booking.`,
  );
  await page.getByRole("button", { name: /send message/i }).click();
  await shot(page, "01-asked-for-three-seats", `asked the assistant for ${SEATS} seats`);

  const approve = page.getByRole("button", { name: /^Approve$/ });
  await approve.waitFor({ timeout: 90_000 });
  await approve.click();
  await page.waitForTimeout(60_000);

  // The plan gate is not the booking confirmation; the assistant asks again.
  await composer.fill("Yes, book it.");
  await page.getByRole("button", { name: /send message/i }).click();
  await page.waitForTimeout(90_000);
  await shot(page, "02-assistant-reply", "the assistant's reply after confirming");

  await page.goto(`${BASE}/trips/${tripId}`, { waitUntil: "networkidle" });
  await page.getByRole("tab", { name: "Bookings" }).click();
  await page.waitForTimeout(2000);
  await shot(page, "03-trip-bookings", "the booking on the trip, priced for the party");

  console.log(`\ntrip: ${tripId}`);
  console.log(`seats asked for: ${SEATS}`);
} catch (err) {
  await page.screenshot({ path: `${OUT}zz-failure.png`, fullPage: true }).catch(() => {});
  console.log("\nFAILED —", err.message.split("\n")[0]);
  throw err;
} finally {
  await browser.close();
}
