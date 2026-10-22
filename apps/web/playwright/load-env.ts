/**
 * Side-effect module: pull `apps/web/.env*` into the Playwright runner process.
 *
 * Import this BEFORE `./e2e-env` in `playwright.config.ts`. Module imports are
 * evaluated in order and before the importing file's own statements, so calling
 * `loadEnvConfig` as a statement in the config would run AFTER `e2e-env` has
 * already read `process.env` — credentials supplied only through `.env.local`
 * would be captured as undefined and every auth spec would silently skip.
 *
 * `loadEnvConfig` is the loader `next dev` itself uses, so precedence matches
 * the app: it never overrides a variable that is already set, which is what lets
 * CI's exported secrets win over any file on the runner.
 *
 * Only Playwright loads this module, so it may rely on `__dirname` (the
 * transpile is CommonJS — see `./e2e-env` for the two-loader story).
 */
import path from "node:path";

import { loadEnvConfig } from "@next/env";

// `dev: true` selects the same file set `next dev` reads, so `.env.local` and
// `.env.development.local` both reach the runner. Left at the default the loader
// runs in production mode and silently ignores `.env.development.local`.
loadEnvConfig(path.join(__dirname, ".."), true);
