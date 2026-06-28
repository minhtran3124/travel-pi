/**
 * Theme e2e — light/dark toggle, OS default, and persistence.
 *
 * Unlike `trip-smoke.spec.ts`, this spec does NOT need the FastAPI backend: it
 * only exercises the `next-themes` ThemeProvider + the header ThemeToggle, which
 * render purely client-side. The Next dev server (:3000) is booted by
 * playwright.config.ts (reused if already running).
 *
 *   # from apps/web — install the browser once, then run only this spec
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   pnpm exec playwright install chromium
 *   pnpm e2e -g "theme"
 *
 * We assert on `<html class="dark">` and the `localStorage` key `"theme"` (set
 * by next-themes). `/trips` page DATA may need the backend, but the header +
 * toggle + html class always render, so the assertions never depend on it.
 */
import { expect, test } from "@playwright/test";

const html = (page: import("@playwright/test").Page) => page.locator("html");
const toggle = (page: import("@playwright/test").Page) =>
  page.getByRole("button", { name: "Toggle theme" });

test.describe("default theme follows the OS color-scheme", () => {
  test.describe("with a dark OS preference", () => {
    test.use({ colorScheme: "dark" });

    test("html gets the dark class", async ({ page }) => {
      await page.goto("/trips");
      await expect(html(page)).toHaveClass(/dark/);
    });
  });

  test.describe("with a light OS preference", () => {
    test.use({ colorScheme: "light" });

    test("html does not get the dark class", async ({ page }) => {
      await page.goto("/trips");
      // The toggle is gated behind client hydration; once it's interactive the
      // theme has resolved, so a missing `dark` class is meaningful (not a race).
      await expect(toggle(page)).toBeVisible();
      await expect(html(page)).not.toHaveClass(/dark/);
    });
  });
});

test.describe("with a light OS preference", () => {
  test.use({ colorScheme: "light" });

  test("toggle flips the theme and persists it to localStorage", async ({
    page,
  }) => {
    await page.goto("/trips");
    await expect(html(page)).not.toHaveClass(/dark/);

    // Light → dark.
    await toggle(page).click();
    await expect(html(page)).toHaveClass(/dark/);
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem("theme")))
      .toBe("dark");

    // Dark → light.
    await toggle(page).click();
    await expect(html(page)).not.toHaveClass(/dark/);
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem("theme")))
      .toBe("light");
  });

  test("dark theme persists across a reload", async ({ page }) => {
    await page.goto("/trips");
    await toggle(page).click();
    await expect(html(page)).toHaveClass(/dark/);

    await page.reload();
    await expect(html(page)).toHaveClass(/dark/);
  });

  test("no FOUC — a persisted dark theme is applied before paint", async ({
    page,
  }) => {
    // Seed the next-themes localStorage key on the origin, then navigate fresh.
    await page.goto("/trips");
    await page.evaluate(() => localStorage.setItem("theme", "dark"));

    // Fresh navigation: next-themes' pre-paint inline script should set the
    // `dark` class synchronously, so it's present immediately (no waiting for
    // network idle / React hydration).
    await page.goto("/trips", { waitUntil: "commit" });
    await expect(html(page)).toHaveClass(/dark/);
  });
});
