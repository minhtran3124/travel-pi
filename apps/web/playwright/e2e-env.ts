/**
 * Shared e2e environment reader — the ONE module that touches `process.env`.
 *
 * Every Playwright file (the setup project + the auth specs) imports its
 * credentials from here, so no other file reads `process.env` directly and
 * there is a single place to reason about a missing-credentials run.
 *
 *   # from apps/web — quick check that this module loads under Node 24
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   node -e "import('./playwright/e2e-env.ts').then(m => console.log(m.hasCreds))"
 *
 * The storage-state path lives in `./storage-state`, not here: this module is
 * loaded two different ways and that one is Playwright-only.
 *
 * This module is loaded two different ways, so it must not mention
 * `import.meta`: Playwright transpiles it to CommonJS (apps/web deliberately has
 * no `"type": "module"`, because adding one breaks the Next build), where
 * `import.meta` is a parse error and `__dirname` is defined; Node's own type
 * stripping loads the same file as ESM, where `__dirname` is undefined. The
 * CommonJS branch is the one Playwright takes. Reading `process.env` at module
 * scope is safe only because `playwright.config.ts` imports `./load-env` before
 * this module; see that file for the ordering rule.
 */

export const E2E_USER_EMAIL: string | undefined = process.env.E2E_USER_EMAIL;
export const E2E_USER_PASSWORD: string | undefined =
  process.env.E2E_USER_PASSWORD;

export const hasCreds: boolean = Boolean(E2E_USER_EMAIL && E2E_USER_PASSWORD);

if (!hasCreds) {
  const missing = [
    E2E_USER_EMAIL ? null : "E2E_USER_EMAIL",
    E2E_USER_PASSWORD ? null : "E2E_USER_PASSWORD",
  ].filter(Boolean);
  process.stderr.write(
    `[e2e-env] missing credentials: ${missing.join(", ")} — auth e2e specs will be skipped\n`,
  );
}
