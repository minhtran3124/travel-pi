/**
 * Theme e2e — light/dark toggle, OS default, and persistence.
 *
 * This spec exercises the `next-themes` ThemeProvider + the header ThemeToggle,
 * which render purely client-side — it needs NO FastAPI backend. It does,
 * however, need an authenticated session: every test navigates to `/trips`
 * because there is no public URL that renders the theme toggle. `/` is
 * `redirect("/trips")`, and `AppShell` renders bare children under `/auth*`, so
 * an unauthenticated visit never shows the header + toggle. The session is
 * produced once by the `setup` project and reused; without e2e credentials the
 * whole file is skipped via the file-scope `test.skip(!hasCreds, …)` below.
 *
 *   # from apps/web — install the browser once, then run only this spec
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   pnpm exec playwright install chromium
 *   E2E_USER_EMAIL=… E2E_USER_PASSWORD=… pnpm e2e -g "theme"
 *
 * We assert on `<html class="dark">` and the `localStorage` key `"theme"` (set
 * by next-themes). `/trips` page DATA may need the backend, but the header +
 * toggle + html class always render, so the assertions never depend on it.
 *
 * This file pins `retries: 0` even under CI. The "no FOUC" test is built on a
 * single attempt: a retry runs against an already-warm route, so a real flash
 * regression would be reported as flaky and the run would still exit 0. Keeping
 * the retry budget at zero here preserves the guarantee; the rest of the suite
 * keeps the config's CI retry.
 */
import { expect, test } from "@playwright/test";

import { hasCreds } from "./e2e-env";

test.describe.configure({ retries: 0 });

// File-scope guard: `/trips` needs an authenticated session (see the header).
// Without e2e credentials the shared storage state is never written, so skip
// the whole file rather than fail on a missing session.
test.skip(!hasCreds, "E2E_USER_EMAIL/E2E_USER_PASSWORD not set");

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
    // `dark` class during initial parse. Read classList ONCE at
    // domcontentloaded (root exists, inline script has run, but the React
    // bundle has NOT hydrated yet) with no retry window — a retrying matcher
    // would also pass if the class were applied late, after hydration, masking
    // a real flash. This fails hard unless the inline script set it pre-paint.
    await page.goto("/trips", { waitUntil: "domcontentloaded" });
    const darkBeforeHydration = await page.evaluate(() =>
      document.documentElement.classList.contains("dark"),
    );
    expect(darkBeforeHydration).toBe(true);
  });
});
