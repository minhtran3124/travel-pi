import { expect, test } from "@playwright/test";

const SHOTS =
  "/private/tmp/claude-501/-Users-minhtran-Documents-minhtran3124-developer-travel-pi/44be981d-95b4-4383-a008-827f6eb376af/scratchpad/uat";

// UAT: one message asking for cafes + restaurants must leave BOTH category tabs
// in the drawer — the first tab must never be replaced by the second.
test("cafes + restaurants stay as two tabs", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open travel assistant" }).click();

  const composer = page.getByRole("textbox", { name: "Message the travel assistant" });
  await composer.fill("Find me good cafes and restaurants in Da Nang");
  await page.getByRole("button", { name: "Send message" }).click();

  const drawer = page.getByRole("region", { name: "Detail panel" });
  await expect(drawer).toBeVisible({ timeout: 180_000 });

  // First category tab appears — remember which one.
  const tabs = drawer.locator("header button:not([aria-label='Hide panel'])");
  await expect(tabs.first()).toBeVisible({ timeout: 120_000 });
  const firstTab = (await tabs.first().innerText()).trim().toLowerCase();
  await page.screenshot({ path: `${SHOTS}/1-first-tab-${firstTab}.png`, fullPage: false });

  // Second category tab arrives — the first one must still be there.
  await expect(tabs).toHaveCount(2, { timeout: 120_000 });
  const names = (await tabs.allInnerTexts()).map((t) => t.trim().toLowerCase());
  expect(names).toContain(firstTab);
  expect(new Set(names).size).toBe(2);
  await page.screenshot({ path: `${SHOTS}/2-two-tabs.png` });

  // Wait for the turn to finish, then capture the final state (chips + drawer).
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible({ timeout: 180_000 });
  await expect(tabs).toHaveCount(2);
  await page.screenshot({ path: `${SHOTS}/3-turn-done-newest-tab-active.png` });

  // Switch to the other tab and prove its content is still rendered.
  const other = names.find((n) => n !== firstTab)!;
  const activeBtn = drawer.locator("header button.bg-ink");
  const active = (await activeBtn.innerText()).trim().toLowerCase();
  const target = active === firstTab ? other : firstTab;
  await drawer.getByRole("button", { name: new RegExp(`^${target}$`, "i") }).click();
  for (const ms of [0, 500, 1500]) {
    await page.waitForTimeout(ms);
    const act = (await activeBtn.innerText()).trim();
    const body = (await drawer.locator(".tp-panel-swap").innerText()).slice(0, 60).replace(/\n/g, " | ");
    console.log(`after click +${ms}ms: active=${act} body="${body}"`);
    await page.screenshot({ path: `${SHOTS}/4-switched-to-${target}-${ms}ms.png` });
  }
  await expect(activeBtn).toHaveText(new RegExp(target, "i"));
  await expect(drawer.locator(".tp-panel-swap")).toContainText(new RegExp(target, "i"));

  // Chip row: one chip per category, titled by category (aria-label "cafe — 4 results (Open)").
  const chips = page.getByRole("button", { name: new RegExp(`^(${firstTab}|${other}) — .*\\(Open\\)$`, "i") });
  await expect(chips).toHaveCount(2);
  await page.screenshot({ path: `${SHOTS}/5-chips-by-category.png` });

  console.log(`UAT tabs: first=${firstTab} all=${JSON.stringify(names)}`);
});
