/**
 * UAT for #156 — a bare flight search must search first and never open a trip;
 * an itinerary request must still open one. Kept with the spec (not in
 * apps/web/playwright/) because it needs a live LLM key, a signed-in Supabase
 * user and the api dashboard, so it must not run in the normal e2e suite.
 *
 * Run recipe (2026-09-08): copy this file to apps/web/playwright/, start the
 * travel-pi web dev server on a free port (:3000 was taken by another project
 * here, so :3001 was used with a small config override setting baseURL and
 * webServer: undefined), keep the Docker api on :8000 with the graph rebuilt
 * after the prompt bump (`docker exec api-api-1 touch app/main.py`), then:
 *
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   DASHBOARD_BASIC_USER=… DASHBOARD_BASIC_PASSWORD=… \
 *     pnpm exec playwright test --config playwright.uat.config.ts uat-gh156
 *
 * Screenshots land in this folder. The dashboard shots were captured with a
 * short standalone script when Playwright's own screenshot step ran long.
 */
import { expect, test, type Page } from "@playwright/test";

import { hasCreds } from "./e2e-env";

const SHOTS =
  "/Users/minhtran/Documents/minhtran3124/developer/travel-pi/specs/gh-156-flight-search-before-create-trip/uat";
const API = "http://localhost:8000";
const TURN_TIMEOUT = 240_000;

test.skip(!hasCreds, "E2E_USER_EMAIL/E2E_USER_PASSWORD not set");
test.describe.configure({ mode: "serial", timeout: 1_200_000 });

async function openFreshChat(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Open travel assistant" }).click();
  await page.getByRole("button", { name: "Expand panel" }).click();
  // Start from an empty thread so the trail/dashboard evidence is this turn's.
  await page.getByRole("button", { name: "Conversation settings" }).click();
  await page.getByRole("menuitem", { name: "New conversation" }).click();
  const cta = page.getByRole("button", { name: "Start new" });
  if (await cta.isVisible({ timeout: 2_000 }).catch(() => false)) await cta.click();
}

async function send(page: Page, text: string) {
  const composer = page.getByRole("textbox", { name: "Message the travel assistant" });
  await composer.fill(text);
  await page.getByRole("button", { name: "Send message" }).click();
  // The send button is replaced by Stop while streaming; back = turn finished.
  await expect(page.getByRole("button", { name: "Stop generating" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible({ timeout: TURN_TIMEOUT });
}

/** Expand the newest activity trail (its toggle is the "Sorted N things…" summary). */
async function latestTrail(page: Page): Promise<string> {
  const toggle = page.getByRole("button", { name: /Sorted .* for your trip/ }).last();
  await expect(toggle).toBeVisible({ timeout: 30_000 });
  await toggle.click();
  const trail = toggle.locator("xpath=..");
  await expect(trail.getByRole("list")).toBeVisible({ timeout: 10_000 });
  return (await trail.innerText()).replace(/\s+/g, " ");
}

/** Open the newest agent run in the api dashboard and return its page text. */
async function latestRunTools(page: Page, shot: string): Promise<string> {
  const user = process.env.DASHBOARD_BASIC_USER ?? "";
  const pass = process.env.DASHBOARD_BASIC_PASSWORD ?? "";
  const ctx = await page.context().browser()!.newContext({
    httpCredentials: user ? { username: user, password: pass } : undefined,
    viewport: { width: 1280, height: 1400 },
  });
  const dash = await ctx.newPage();
  await dash.goto(`${API}/dashboard/agent-runs`);
  await dash.locator("a.run-link").first().click();
  await dash.waitForURL(/\/dashboard\/agent-runs\/[^/]+$/);
  // Read the evidence first: a slow screenshot must not cost us the assertion.
  const text = (await dash.locator("body").innerText()).replace(/\s+/g, " ");
  await dash.screenshot({ path: `${SHOTS}/${shot}`, timeout: 30_000 }).catch(() => {});
  await ctx.close();
  return text;
}

test("1 · bare flight search: search_flights runs, create_trip does not", async ({ page }) => {
  await openFreshChat(page);

  await send(page, "Tôi muốn bay từ Hà Nội đi Phú Quốc");
  await page.screenshot({ path: `${SHOTS}/1-turn1-asks-for-date.png` });

  await send(page, "Ngày 25 tháng 3 năm 2027 nhé, cho 2 người lớn");
  // The flights drawer opens on its own; its region name follows the conversation
  // language (vi here), so accept both labels. It must carry the real search result.
  const drawer = page.getByRole("region", { name: /Detail panel|Bảng chi tiết/ });
  await expect(drawer).toBeVisible({ timeout: 30_000 });
  await expect(drawer).toContainText("HAN → PQC");
  await page.screenshot({ path: `${SHOTS}/2-turn2-flights-panel.png` });

  const trail = await latestTrail(page);
  console.log(`trail (turn 2): ${trail}`);
  await page.screenshot({ path: `${SHOTS}/3-turn2-activity-trail.png` });
  expect(trail).toContain("Searching flights");
  expect(trail).not.toContain("Updating your trip");

  const tools = await latestRunTools(page, "4-dashboard-run-search-only.png");
  console.log(`dashboard run tools: ${tools.match(/[a-z_]+_(flights|trip|date|summary)/g)?.join(", ")}`);
  expect(tools).toContain("search_flights");
  expect(tools).not.toContain("create_trip");
});

test("2 · itinerary request still opens a trip", async ({ page }) => {
  await openFreshChat(page);

  await send(
    page,
    "Lên kế hoạch 3 ngày ở Đà Nẵng từ 10/03/2027 đến 12/03/2027 cho 2 người lớn, lưu thành chuyến đi giúp mình",
  );
  const trail = await latestTrail(page);
  console.log(`trail (itinerary): ${trail}`);
  await page.screenshot({ path: `${SHOTS}/5-itinerary-request-trail.png` });

  const tools = await latestRunTools(page, "6-dashboard-run-create-trip.png");
  console.log(`dashboard run tools: ${tools.match(/[a-z_]+_(flights|trip|date|summary|item)/g)?.join(", ")}`);
  expect(tools).toContain("create_trip");
});
