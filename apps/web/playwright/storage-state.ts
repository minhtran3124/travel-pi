/**
 * Where the shared browser session is written and read.
 *
 * Anchored to this file's own directory, never to `process.cwd()`: a
 * cwd-relative storage-state path is the documented cause of a setup project
 * passing locally and failing on a CI runner
 * (https://github.com/microsoft/playwright/issues/32302).
 *
 * Only Playwright imports this module, and Playwright transpiles it to
 * CommonJS, so `__dirname` is defined. If some other loader ever pulls it in as
 * ESM, that is a mistake worth failing on rather than silently answering with a
 * cwd-relative guess.
 */
import path from "node:path";

if (typeof __dirname !== "string") {
  throw new Error(
    "storage-state.ts must be loaded by Playwright (CommonJS); __dirname is undefined here.",
  );
}

export const STORAGE_STATE: string = path.join(__dirname, ".auth", "user.json");
