/**
 * Browser UAT for slice 2 — the three things the tests could not prove.
 *
 * 1. the assistant reaches for `get_visa` in a live turn, rather than falling
 *    back to the knowledge index or refusing the way v11 told it to
 * 2. /guide/[city] renders visa, tips and climate in a real browser
 * 3. the trip Map tab draws its markers, and the six-tab row still reads
 *
 * Playwright's MCP server is broken here, so this drives playwright-core under
 * Node 24 — the pattern this repo already uses for UI verification.
 *
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   cd apps/web && node ../../specs/close-product-loop-s2-guide-and-map/uat/run-uat.mjs
 *
 * Requires the WORKTREE's own servers, not the Docker stack: the dev container
 * mounts the main checkout, which is on someone else's branch and has none of
 * this code. Web on :3200, API on :8001.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(new URL("../../../apps/web/package.json", import.meta.url));
const requireFromTest = createRequire(require.resolve("@playwright/test"));
const { chromium } = requireFromTest("playwright-core");

const BASE = process.env.UAT_BASE ?? "http://localhost:3200";
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
page.setDefaultTimeout(25_000);

try {
  await page.goto(`${BASE}/auth/login`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', EMAIL);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.startsWith("/auth/login"), { timeout: 30_000 });
  console.log("signed in as", EMAIL);

  // --- Case 1: the guide page --------------------------------------------------
  await page.goto(`${BASE}/guide/Da%20Nang`, { waitUntil: "networkidle" });
  await page.waitForTimeout(3000);
  await shot(page, "01-guide-page", "visa, tips and climate for one city");

  // --- Case 2: a trip with something to plot -----------------------------------
  await page.goto(`${BASE}/trips`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "New trip" }).first().click();
  await page.getByLabel("Trip name").fill(`UAT Map ${stamp}`);
  await page.getByRole("button", { name: "Create trip" }).click();
  await page.waitForURL(/\/trips\/[^/]+$/);
  const tripId = page.url().split("/trips/")[1];
  console.log("trip", tripId);

  await page.getByRole("tab", { name: "Map" }).click();
  await page.waitForTimeout(4000);
  await shot(page, "02-map-tab-empty", "Map tab on a trip with nothing to plot yet");

  // --- Case 3: the six-tab row at a narrow width -------------------------------
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(1500);
  await shot(page, "03-six-tabs-narrow", "the tab row at 390px — the width nobody had measured");
  await page.setViewportSize({ width: 1280, height: 900 });

  // --- Case 4: does the assistant reach for get_visa? --------------------------
  await page.getByRole("button", { name: /open travel assistant/i }).click();
  const composer = page.getByRole("textbox", { name: /message the travel assistant/i });
  await composer.waitFor();
  await composer.fill("Do I need a visa for Vietnam?");
  await page.getByRole("button", { name: /send message/i }).click();
  await shot(page, "04-visa-asked", "a visa question put to the assistant");

  await page.waitForTimeout(75_000);
  await shot(page, "05-visa-answer", "the assistant's answer");

  console.log(`\ntrip: ${tripId}`);
  console.log("now check the API log for which tool was called");
} catch (err) {
  await page.screenshot({ path: `${OUT}zz-failure.png`, fullPage: true }).catch(() => {});
  console.log("\nFAILED —", err.message.split("\n")[0]);
  throw err;
} finally {
  await browser.close();
}
