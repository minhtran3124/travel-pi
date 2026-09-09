/**
 * UAT for #147 — run recipe (not part of `pnpm e2e`; it lives here, not in
 * apps/web/playwright, so it never joins the e2e suite).
 *
 *   # 1. Docker api on :8000 and the travel-pi Next dev server both running.
 *   #    Check which port is travel-pi's — another project may hold :3000:
 *   #      curl -s localhost:3000 | grep -o "<title>[^<]*"
 *   # 2. Copy this file into apps/web/playwright/, point playwright.config.ts's
 *   #    `baseURL` + `webServer.url` at the right port, then:
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   cd apps/web && pnpm exec playwright test gh147-hotel-uat --project=chromium --reporter=line
 *   # 3. Revert playwright.config.ts and remove the copied spec afterwards.
 *
 * Screenshots land in specs/gh-147-dated-hotel-availability-routing/uat/.
 */
import { expect, test } from "@playwright/test";

/**
 * UAT for #147 — the concierge answers a hotel question with and without dates.
 *
 * Turn 1 carries no dates: the assistant must show hotels from the dateless
 * catalog browse and must NOT interrogate the traveller for check-in/check-out
 * (the MIN-51 regression this branch was most exposed to).
 *
 * Turn 2 supplies dates and party size: the assistant must answer with real
 * availability and must NOT claim it cannot check room availability — the exact
 * sentence issue #147 reported.
 */
const SHOTS = "../../specs/gh-147-dated-hotel-availability-routing/uat";

const CANNOT_CHECK =
  /can'?t check (real )?(room )?availability|cannot check (real )?(room )?availability|không (thể )?kiểm tra (được )?phòng trống/i;

test("hotel search without dates, then with dates", async ({ page }) => {
  test.setTimeout(360_000);

  await page.goto("/");
  await page.getByRole("button", { name: "Open travel assistant" }).click();

  const composer = page.getByRole("textbox", {
    name: "Message the travel assistant",
  });
  const send = page.getByRole("button", { name: "Send message" });

  // ---- Turn 1: no dates -------------------------------------------------
  await composer.fill("I'm looking for a hotel in Da Nang");
  await send.click();

  const drawer = page.getByRole("region", { name: "Detail panel" });
  await expect(drawer).toBeVisible({ timeout: 180_000 });
  await expect(send).toBeVisible({ timeout: 240_000 });

  // The dateless catalog projection: no stay echoed, nights = 0.
  await expect(drawer).toContainText(/0 nights/, { timeout: 60_000 });
  await page.screenshot({ path: `${SHOTS}/1-no-dates-browse.png`, fullPage: false });

  const turn1 = await page.locator("main").innerText();
  console.log("=== TURN 1 ===\n" + turn1.slice(-1200));
  // No date interrogation: the assistant must not answer a dateless ask with a
  // demand for check-in/check-out (the MIN-51 regression).
  expect(turn1, "a dateless hotel ask must not be answered with a date demand").not.toMatch(
    /when (are|do) you (plan to )?(check|travel|arrive)|what (are your|dates)|check-?in date\?/i,
  );

  // ---- Turn 2: dates + party -------------------------------------------
  await composer.fill(
    "Check-in March 10 2027, check-out March 14 2027, 2 adults, 1 child",
  );
  await send.click();
  await expect(send).toBeVisible({ timeout: 240_000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${SHOTS}/2-dated-availability.png`, fullPage: false });

  const turn2 = await page.locator("main").innerText();
  console.log("=== TURN 2 ===\n" + turn2.slice(-1800));

  const reply = turn2.slice(turn1.length);
  expect(reply, "the assistant must not deny being able to check availability").not.toMatch(
    CANNOT_CHECK,
  );

  // The dated panel echoes the exact stay the traveller gave — the catalog
  // projection cannot produce this (it has no dates and 0 nights).
  await expect(drawer).toContainText("2027-03-10", { timeout: 60_000 });
  await expect(drawer).toContainText("2027-03-14");
  await expect(drawer).toContainText(/4 nights/);
  await expect(drawer).toContainText(/available/i);
  await page.screenshot({ path: `${SHOTS}/3-dated-panel.png`, fullPage: true });
});
