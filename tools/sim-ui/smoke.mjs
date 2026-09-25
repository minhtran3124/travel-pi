#!/usr/bin/env node
// UI smoke: replay a fixture over the real bus, then assert the lobby renders it.
// Node 24 ESM. playwright-core is not hoisted, so it is resolved from the pnpm
// store; exit 2 when it is absent, exit 1 on any assertion failure, exit 0 on pass.
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const FINISHED_ID = "p1";
const FIXTURE = path.join(REPO_ROOT, "tools", "sim-ui", "fixtures", "transcript.jsonl");
const SCREENSHOT = path.join(REPO_ROOT, "tools", "sim-ui", "smoke.png");

function resolvePlaywright() {
  const pnpmDir = path.join(REPO_ROOT, "node_modules", ".pnpm");
  let entries;
  try {
    entries = readdirSync(pnpmDir);
  } catch {
    return null;
  }
  const match = entries.find((n) => n.startsWith("playwright-core@"));
  if (!match) return null;
  return require(path.join(pnpmDir, match, "node_modules", "playwright-core"));
}

function readPort(child) {
  return new Promise((resolve, reject) => {
    let out = "";
    let err = "";
    const timer = setTimeout(
      () => reject(new Error("timed out waiting for PORT= from replay_fixture")),
      20000,
    );
    child.stdout.on("data", (d) => {
      out += d.toString();
      const m = out.match(/PORT=(\d+)/);
      if (m) {
        clearTimeout(timer);
        resolve(Number(m[1]));
      }
    });
    child.stderr.on("data", (d) => {
      err += d.toString();
    });
    child.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`replay_fixture exited early (code ${code}): ${err.trim()}`));
    });
  });
}

async function main() {
  const pw = resolvePlaywright();
  if (!pw) {
    console.error(
      "playwright-core not found under node_modules/.pnpm/playwright-core@*",
    );
    process.exit(2);
  }

  const child = spawn(
    path.join(REPO_ROOT, ".venv", "bin", "python"),
    ["-m", "sim.replay_fixture", FIXTURE],
    { cwd: path.join(REPO_ROOT, "apps", "api") },
  );

  let browser = null;
  try {
    const port = await readPort(child);
    browser = await pw.chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.goto(`http://localhost:${port}/`, { waitUntil: "load" });
    await page.click(`#roster tr[data-id="${FINISHED_ID}"]`, { timeout: 15000 });
    await page.waitForFunction(
      () => {
        const done = document.querySelector("#done-count");
        const lines = document.querySelectorAll("#transcript li");
        return !!done && done.textContent.trim() === "1/2" && lines.length >= 4;
      },
      { timeout: 15000 },
    );
    await page.screenshot({ path: SCREENSHOT });
  } catch (e) {
    if (browser) await browser.close().catch(() => {});
    if (!child.killed) child.kill("SIGKILL");
    console.error(`SMOKE FAIL: ${e.message}`);
    process.exit(1);
  }

  await browser.close();
  if (!child.killed) child.kill("SIGKILL");
  console.log("SMOKE PASS");
  process.exit(0);
}

main();
