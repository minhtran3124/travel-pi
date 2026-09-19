/**
 * Browser UAT for trip-research-deep-agent — one screenshot per state the
 * Research tab can show a real user.
 *
 * Walks: log in → open a trip → Research tab (empty) → start a run → live
 * progress (todos, subagent/tool chips, rubric verdict) → the dossier file
 * list with one file open → the proposal panel.
 *
 * Playwright MCP is broken in this environment, so this drives playwright-core
 * directly under Node 24 (same pattern as user-feedback-v1/uat).
 *
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   cd apps/web && node ../../specs/trip-research-deep-agent/uat/run-uat.mjs
 *
 * Requires the web dev server on UAT_BASE (default :3000), the API on :8000
 * with a real LLM key, and E2E_USER_EMAIL / E2E_USER_PASSWORD for a PREMIUM
 * user (the tab is premium-gated; a free user gets the locked empty state).
 */
import { createRequire } from "node:module";

const req = createRequire(new URL("../../../apps/web/package.json", import.meta.url));
const reqFromTest = createRequire(req.resolve("@playwright/test"));
const chromium = reqFromTest("playwright-core").chromium;

const BASE = process.env.UAT_BASE || "http://localhost:3000";
const OUT = new URL("./", import.meta.url).pathname;
const EMAIL = process.env.E2E_USER_EMAIL;
const PASSWORD = process.env.E2E_USER_PASSWORD;
// A full fan-out run measured ~11 min end to end; give the UAT real headroom.
const RUN_TIMEOUT_MS = Number(process.env.UAT_RUN_TIMEOUT_MS || 1500000);
if (!EMAIL || !PASSWORD) throw new Error("set E2E_USER_EMAIL and E2E_USER_PASSWORD");

async function shot(page, name, note) {
  await page.screenshot({ path: OUT + name + ".png", fullPage: true });
  console.log("  captured " + name + ".png - " + note);
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(30000);

try {
  console.log("1. sign in");
  await page.goto(BASE + "/auth/login", { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', EMAIL);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => u.pathname.indexOf("/auth/login") !== 0, { timeout: 30000 });

  console.log("2. open a trip");
  await page.goto(BASE + "/trips", { waitUntil: "networkidle" });
  const tripLink = page.locator('a[href^="/trips/"]').first();
  await tripLink.waitFor();
  await tripLink.click();
  await page.waitForURL(/\/trips\/[^/]+$/);
  const tripId = new URL(page.url()).pathname.split("/").pop();
  console.log("   trip " + tripId);

  console.log("3. Research tab");
  await page.getByRole("tab", { name: "Research", exact: true }).click();
  await page.waitForTimeout(1500);
  await shot(page, "01-research-empty", "empty state before any run");

  console.log("4. start the run");
  await page.getByRole("button", { name: "Research this trip" }).click();
  // The progress card appears as soon as the SSE stream delivers its first event.
  await page.getByText("Researching your trip…").first().waitFor({ timeout: 60000 });
  await page.waitForTimeout(20000);
  await shot(page, "02-research-progress", "live progress: todos + subagent/tool chips");

  console.log("5. wait for the first dossier file");
  await page.getByText("Research files").waitFor({ timeout: RUN_TIMEOUT_MS });
  await page.waitForTimeout(3000);
  await shot(page, "03-research-files", "dossier files appearing while the run is live");

  console.log("6. wait for the run to settle");
  await page
    .getByText("Researching your trip…")
    .first()
    .waitFor({ state: "detached", timeout: RUN_TIMEOUT_MS });
  await page.waitForTimeout(2000);
  await shot(page, "04-research-done", "run finished: files + proposal");

  console.log("7. open a dossier file");
  const firstFile = page.locator('li > button[aria-pressed]').first();
  await firstFile.click();
  await page.waitForTimeout(2500);
  await shot(page, "05-research-file-open", "a dossier file rendered in the viewer");

  console.log("UAT OK - screenshots in " + OUT);
} catch (err) {
  await shot(page, "99-failure", "state at failure");
  console.error("UAT FAILED: " + err.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
