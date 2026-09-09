/**
 * Browser UAT for the S1 booking slice — one screenshot per case.
 *
 * The product shape this checks: /flights and /hotels are BROWSE-ONLY, and all
 * booking happens through the chatbot, which stamps the active trip onto the
 * booking so it shows up on that trip.
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
 * The chat booking case needs a premium account — the booking sub-agent is
 * premium-only. On a free account it captures the assistant's refusal instead,
 * which is also worth seeing.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

// This file lives under specs/, so bare-specifier resolution would look for
// node_modules next to it. playwright-core is a transitive dependency of
// @playwright/test, so pnpm keeps it in the store rather than hoisting it;
// resolve it from @playwright/test, which apps/web depends on directly.
const require = createRequire(new URL("../../../apps/web/package.json", import.meta.url));
const requireFromTest = createRequire(require.resolve("@playwright/test"));
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

async function shot(page, name, note) {
  await page.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
  console.log(`  captured ${name}.png — ${note}`);
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
page.setDefaultTimeout(20_000);

try {
  // --- Sign in ---------------------------------------------------------------
  await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', EMAIL);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.startsWith("/auth/login"), { timeout: 30_000 });
  console.log("signed in as", EMAIL);

  // --- Case 1: the two nav entries -------------------------------------------
  await page.goto(`${BASE}/trips`, { waitUntil: "networkidle" });
  await shot(page, "01-nav-flights-hotels", "Flights and Hotels appear in the app nav");

  // --- Create a trip the chat booking can attach to --------------------------
  await page.getByRole("button", { name: "New trip" }).first().click();
  await page.getByLabel("Trip name").fill(`UAT Trip ${stamp}`);
  await page.getByRole("button", { name: "Create trip" }).click();
  await page.waitForURL(/\/trips\/[^/]+$/);
  const tripId = page.url().split("/trips/")[1];
  console.log("trip", tripId);

  const departureDate = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);

  // --- Case 2: /flights browses, and offers no way to act --------------------
  await page.goto(`${BASE}/flights`, { waitUntil: "networkidle" });
  await page.getByLabel("Origin").fill("DAD");
  await page.getByLabel("Destination").fill("SGN");
  await page.getByLabel("Departure date").fill(departureDate);
  await page.getByRole("button", { name: "Search flights" }).click();
  await page.getByText(/ask the assistant/i).first().waitFor();
  console.log("  /flights Book buttons:", await page.getByRole("button", { name: "Book" }).count(), "(want 0)");
  await shot(page, "02-flights-browse-only", "results render; no Book control, only the assistant hint");

  // --- Case 3: /hotels, same -------------------------------------------------
  await page.goto(`${BASE}/hotels`, { waitUntil: "networkidle" });
  await page.getByLabel("City").fill("Da Nang");
  await page.getByLabel("Check-in").fill(departureDate);
  await page.getByLabel("Check-out").fill(
    new Date(Date.now() + 32 * 864e5).toISOString().slice(0, 10),
  );
  await page.getByRole("button", { name: "Search hotels" }).click();
  await page.getByText(/ask the assistant/i).first().waitFor();
  console.log("  /hotels Book buttons:", await page.getByRole("button", { name: "Book" }).count(), "(want 0)");
  await shot(page, "03-hotels-browse-only", "results render; no Book control, only the assistant hint");

  // --- Case 4: book through the chatbot, from the trip's own page ------------
  // Opening the assistant on the trip page is what puts that trip into the
  // agent's state, which is what the booking tools now stamp onto the booking.
  await page.goto(`${BASE}/trips/${tripId}`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /open travel assistant/i }).click();
  const composer = page.getByRole("textbox", { name: /message the travel assistant/i });
  await composer.waitFor();
  await composer.fill(
    `Book the cheapest flight from DAD to SGN on ${departureDate} for this trip. ` +
      `Passenger UAT Tester, email uat-${stamp}@example.com, phone 0900000000. ` +
      `Please confirm the booking.`,
  );
  await page.getByRole("button", { name: /send message/i }).click();
  await shot(page, "04-chat-booking-asked", "the booking request sent to the assistant");

  // Booking is human-in-the-loop: the agent stops and asks before it spends
  // money. Capture that gate, then approve it — clicking Approve IS the case.
  const approve = page.getByRole("button", { name: /^Approve$/ });
  await approve.waitFor({ timeout: 90_000 });
  await shot(page, "05-chat-booking-approval-gate", "the assistant asks before booking");
  await approve.click();

  await page.waitForTimeout(60_000);

  // The plan-approval gate is not the booking confirmation: the assistant still
  // asks for an explicit go-ahead before it spends money, which is the
  // "never confirm a booking without explicit approval" guardrail doing its job.
  // Answer it, the way a traveller would.
  await composer.fill("Yes, book it.");
  await page.getByRole("button", { name: /send message/i }).click();
  await page.waitForTimeout(90_000);
  await shot(page, "06-chat-booking-done", "the assistant's reply after confirming");

  // --- Case 5: does the trip now show it? ------------------------------------
  await page.goto(`${BASE}/trips/${tripId}`, { waitUntil: "networkidle" });
  await page.getByRole("tab", { name: "Bookings" }).click();
  await page.waitForTimeout(2000);
  await shot(page, "07-trip-bookings-after-chat", "the trip's Bookings tab after booking in chat");

  await page.getByRole("tab", { name: "Budget" }).click();
  await page.waitForTimeout(2000);
  await shot(page, "08-trip-budget-after-chat", "booked total on the trip after booking in chat");

  console.log(`\nscreenshots written to ${OUT}`);
  console.log(`trip: ${tripId}`);
} catch (err) {
  await page.screenshot({ path: `${OUT}zz-failure.png`, fullPage: true }).catch(() => {});
  console.log("\nFAILED —", err.message.split("\n")[0]);
  throw err;
} finally {
  await browser.close();
}
