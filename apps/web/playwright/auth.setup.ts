/**
 * Sign-in setup project — produces the shared storage state every auth spec
 * reuses. The chromium project depends on this project, so this signs in ONCE
 * and writes the session to `STORAGE_STATE`; the specs then start already
 * authenticated instead of re-driving the login form.
 *
 * Prerequisite: the Supabase e2e user (`E2E_USER_EMAIL`) exists with a
 * CONFIRMED email, and `E2E_USER_PASSWORD` is its password. Without both, the
 * whole setup + auth suite is skipped (see the file-scope `setup.skip` below).
 *
 *   # from apps/web — install the browser once, then run only the setup project
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   pnpm exec playwright install chromium
 *   E2E_USER_EMAIL=… E2E_USER_PASSWORD=… pnpm e2e --project=setup
 *
 * The skip guard is at FILE SCOPE, not inside the test body: `storageState` is
 * read when the dependent project's context fixture is created, so a body-level
 * guard would still leave the specs hitting a missing storage-state file.
 */
import { test as setup } from "@playwright/test";

import { E2E_USER_EMAIL, E2E_USER_PASSWORD, STORAGE_STATE, hasCreds } from "./e2e-env";

setup.skip(!hasCreds, "E2E_USER_EMAIL/E2E_USER_PASSWORD not set");

setup("sign in and save the storage state", async ({ page }) => {
  await page.goto("/auth/login");

  await page.getByLabel("Email").fill(E2E_USER_EMAIL!);
  await page.getByLabel("Password").fill(E2E_USER_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();

  // A successful sign-in redirects away from /auth/login. A wrong password keeps
  // the page here and renders a role="alert"; surface its text on timeout so the
  // failure is legible instead of a bare "waitForURL exceeded".
  try {
    await page.waitForURL((url) => !url.pathname.startsWith("/auth/login"));
  } catch (error) {
    const alert = page.getByRole("alert");
    const detail = (await alert.count())
      ? await alert.first().innerText()
      : "(no alert shown)";
    throw new Error(`Sign-in did not leave /auth/login — alert: ${detail}`, {
      cause: error,
    });
  }

  await page.context().storageState({ path: STORAGE_STATE });
});
