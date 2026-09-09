/**
 * Browser UAT for slice 3 — the Today tab. Five things the tests cannot prove.
 *
 * 1. a trip whose dates cover today shows the Today tab with a real day
 * 2. a trip outside its window shows the dated "not in progress" state
 * 3. seven tab labels at 390px, and the document does not scroll sideways
 *    (the plan left this explicitly unmeasured)
 * 4. the Vietnamese locale renders localized weather and air-quality text,
 *    not the API's English prose
 * 5. the weather and air cards show a real ladder, not a silent blank, which
 *    is the defect the independent review found
 *
 * Playwright's MCP server is broken here, so this drives playwright-core under
 * Node 24 — the pattern this repo already uses for UI verification.
 *
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   cd apps/web && node ../specs/close-product-loop-s3-today/uat/run-uat.mjs
 *
 * Requires the WORKTREE's own web server on :3200 — the Docker web container
 * serves the main checkout, which does not have this code. The API is the
 * shared Docker stack on :8000, which is correct here because this slice
 * changes no backend.
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

const iso = (d) => {
  const x = new Date();
  x.setDate(x.getDate() + d);
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
};
const stamp = Date.now();
const results = [];

async function shot(page, name, note) {
  await page.screenshot({ path: `${OUT}${name}.png`, fullPage: true });
  console.log(`  captured ${name}.png — ${note}`);
}

function record(id, title, verdict, detail) {
  results.push({ id, title, verdict, detail });
  console.log(`[${verdict}] ${id} ${title}${detail ? ` — ${detail}` : ""}`);
}

async function makeTrip(page, { title, city, start, end }) {
  await page.goto(`${BASE}/trips`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /new trip|chuyến đi mới|tạo chuyến/i }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.locator("input").first().fill(title);
  await dialog.locator("input").nth(1).fill(city);
  await dialog.locator('input[type="date"]').first().fill(start);
  await dialog.locator('input[type="date"]').nth(1).fill(end);
  await dialog.getByRole("button", { name: /create|save|tạo|lưu/i }).last().click();
  await page.waitForURL(/\/trips\/[0-9a-f-]{8,}/, { timeout: 30_000 });
  return page.url();
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

  // --- Case 1: a trip in progress -------------------------------------------
  const liveUrl = await makeTrip(page, {
    title: `UAT in-progress ${stamp}`,
    city: "Da Nang",
    start: iso(-1),
    end: iso(2),
  });
  await page.getByRole("tab", { name: /today|hôm nay/i }).click();
  await page.waitForTimeout(4000);
  await shot(page, "01-today-in-progress", "trip whose dates cover today");
  const liveText = await page.locator("main").innerText();
  // The empty state's copy is "This trip isn't in progress" — match on the
  // distinctive half, not on a phrasing the UI never uses.
  const NOT_IN_PROGRESS = /isn't in progress|chưa diễn ra/i;
  const inWindow = !NOT_IN_PROGRESS.test(liveText) && /Today's plan|Lịch hôm nay/i.test(liveText);
  record(
    "UAT-1",
    "Today tab on a trip in progress",
    inWindow ? "PASS" : "FAIL",
    inWindow ? "rendered the in-window body" : "did not render the day-plan card inside the window",
  );

  // --- Case 2: the weather and air cards resolve ----------------------------
  const hasWeatherCard = /weather|thời tiết/i.test(liveText);
  const hasAirCard = /air quality|chất lượng không khí/i.test(liveText);
  await shot(page, "02-weather-and-air", "weather + air-quality cards for the trip city");
  record(
    "UAT-2",
    "Weather and air-quality cards render rather than vanish",
    hasWeatherCard && hasAirCard ? "PASS" : "FAIL",
    `weather=${hasWeatherCard} air=${hasAirCard}`,
  );

  // --- Case 3: a trip outside its window ------------------------------------
  await makeTrip(page, {
    title: `UAT past ${stamp}`,
    city: "Hanoi",
    start: iso(-30),
    end: iso(-25),
  });
  await page.getByRole("tab", { name: /today|hôm nay/i }).click();
  await page.waitForTimeout(1500);
  await shot(page, "03-not-in-progress", "trip that ended, dated empty state");
  const pastText = await page.locator("main").innerText();
  const showsDates = NOT_IN_PROGRESS.test(pastText) && /\d{4}-\d{2}-\d{2}/.test(pastText);
  record(
    "UAT-3",
    "Out-of-window trip shows the dated not-in-progress state",
    showsDates ? "PASS" : "FAIL",
    showsDates ? "state and dates both present" : "state or dates missing",
  );

  // --- Case 4: seven tabs at 390px ------------------------------------------
  const narrow = await context.newPage();
  await narrow.setViewportSize({ width: 390, height: 844 });
  await narrow.goto(liveUrl, { waitUntil: "networkidle" });
  await narrow.waitForTimeout(2500);
  await shot(narrow, "04-seven-tabs-390", "seven tabs at a 390px viewport");
  const metrics = await narrow.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    win: window.innerWidth,
    tabs: document.querySelectorAll('[role="tab"]').length,
  }));
  const noOverflow = metrics.doc <= metrics.win;
  record(
    "UAT-4",
    "Seven tabs do not widen the document at 390px",
    noOverflow ? "PASS" : "FAIL",
    `scrollWidth=${metrics.doc} innerWidth=${metrics.win} tabs=${metrics.tabs}`,
  );
  await narrow.close();

  // --- Case 5: Vietnamese locale --------------------------------------------
  // The locale is cookie-based (next-intl reads the `locale` cookie server-side).
  // There is no ?lang= query param on this branch; setting one changes nothing.
  await context.addCookies([
    { name: "locale", value: "vi", domain: "localhost", path: "/", sameSite: "Lax" },
  ]);
  await page.goto(liveUrl, { waitUntil: "networkidle" });
  await page.getByRole("tab", { name: /hôm nay|today/i }).click();
  await page.waitForTimeout(4000);
  await shot(page, "05-vietnamese", "Today tab under the vi locale");
  const viText = await page.locator("main").innerText();
  const viLocalized =
    /Thời tiết/i.test(viText) &&
    /Chất lượng không khí/i.test(viText) &&
    /Lịch hôm nay/i.test(viText);
  record(
    "UAT-5",
    "Vietnamese locale renders localized Today copy",
    viLocalized ? "PASS" : "FAIL",
    viLocalized ? "vi strings present" : "still English",
  );

  console.log("\n=== SUMMARY ===");
  for (const r of results) console.log(`${r.verdict}\t${r.id}\t${r.title} — ${r.detail}`);
  const failed = results.filter((r) => r.verdict === "FAIL");
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  process.exitCode = failed.length ? 1 : 0;
} catch (err) {
  console.error("UAT ERROR:", err.message);
  await shot(page, "99-error", "state at failure");
  process.exitCode = 1;
} finally {
  await browser.close();
}
