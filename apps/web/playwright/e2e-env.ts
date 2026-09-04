/**
 * Shared e2e environment reader — the ONE module that touches `process.env`.
 *
 * Every Playwright file (the setup project + the auth specs) imports its
 * credentials and storage-state path from here, so no other file reads
 * `process.env` directly and there is a single place to reason about a
 * missing-credentials run.
 *
 *   # from apps/web — quick check that this module loads under Node 24
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   node -e "import('./playwright/e2e-env.ts').then(m => console.log(m.hasCreds, m.STORAGE_STATE))"
 *
 * `STORAGE_STATE` is resolved from THIS file's directory (via
 * `import.meta.url`), never from `process.cwd()`: a cwd-relative storage-state
 * path is the documented cause of the setup project passing locally but failing
 * on a CI runner (microsoft/playwright#32302).
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

export const E2E_USER_EMAIL: string | undefined = process.env.E2E_USER_EMAIL;
export const E2E_USER_PASSWORD: string | undefined =
  process.env.E2E_USER_PASSWORD;

export const hasCreds: boolean = Boolean(E2E_USER_EMAIL && E2E_USER_PASSWORD);

const here = path.dirname(fileURLToPath(import.meta.url));
export const STORAGE_STATE: string = path.join(here, ".auth", "user.json");

if (!hasCreds) {
  const missing = [
    E2E_USER_EMAIL ? null : "E2E_USER_EMAIL",
    E2E_USER_PASSWORD ? null : "E2E_USER_PASSWORD",
  ].filter(Boolean);
  process.stderr.write(
    `[e2e-env] missing credentials: ${missing.join(", ")} — auth e2e specs will be skipped\n`,
  );
}
