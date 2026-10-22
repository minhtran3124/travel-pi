#!/usr/bin/env node
// UI smoke: replay a fixture over the real bus, then assert the lobby renders it.
// Node 24 ESM. playwright-core is not hoisted, so it is resolved from the pnpm
// store; exit 2 when it is absent, exit 1 on any failure, exit 0 on pass.
//
// The click is load-bearing: the finished traveller (p1) is selected by default,
// so we first select the queued traveller (p2) and confirm the panel switches to
// it, then select p1 and assert the finished-batch state.
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const FINISHED_ID = "p1";
const FINISHED_NAME = "Aoi Tanaka";
const QUEUED_ID = "p2";
const QUEUED_NAME = "Bruno Costa";
const FIXTURE = path.join(REPO_ROOT, "tools", "sim-ui", "fixtures", "transcript.jsonl");
const SCREENSHOT = path.join(REPO_ROOT, "tools", "sim-ui", "smoke.png");

function resolvePlaywright() {
  const pnpmDir = path.join(REPO_ROOT, "node_modules", ".pnpm");
  let entries;
  try {
    entries = readdirSync(pnpmDir).filter((n) => n.startsWith("playwright-core@")).sort();
  } catch {
    return null;
  }
  if (!entries.length) return null;
  try {
    return require(path.join(pnpmDir, entries[0], "node_modules", "playwright-core"));
  } catch {
    return null;
  }
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
    child.on("error", (e) => {
      clearTimeout(timer);
      reject(e);
    });
    child.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`replay_fixture exited early (code ${code}): ${err.trim()}`));
    });
  });
}

function killChild(child) {
  return new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) return resolve();
    let done = false;
    const finish = () => {
      if (!done) {
        done = true;
        resolve();
      }
    };
    child.once("exit", finish);
    child.kill("SIGTERM");
    setTimeout(() => {
      if (!done) {
        try {
          child.kill("SIGKILL");
        } catch {}
        finish();
      }
    }, 2000);
  });
}

async function main() {
  const pw = resolvePlaywright();
  if (!pw) {
    console.error("playwright-core not found under node_modules/.pnpm/playwright-core@*");
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

    // Select the queued traveller first and confirm the panel switched to it.
    await page.click(`#roster tr[data-id="${QUEUED_ID}"]`, { timeout: 15000 });
    await page.waitForFunction(
      (name) => {
        const card = document.querySelector("#card");
        return !!card && card.textContent.includes(name);
      },
      QUEUED_NAME,
      { timeout: 15000 },
    );

    // Now select the finished traveller and assert the batch/transcript state.
    await page.click(`#roster tr[data-id="${FINISHED_ID}"]`, { timeout: 15000 });
    await page.waitForFunction(
      (name) => {
        const card = document.querySelector("#card");
        const done = document.querySelector("#done-count");
        const lines = document.querySelectorAll("#transcript li");
        return (
          !!card &&
          card.textContent.includes(name) &&
          !!done &&
          done.textContent.trim() === "1/2" &&
          document.querySelector("#batch-id").textContent.trim() === "20260925T000000Z" &&
          lines.length >= 4
        );
      },
      FINISHED_NAME,
      { timeout: 15000 },
    );

    await page.screenshot({ path: SCREENSHOT });
    console.log("SMOKE PASS");
  } finally {
    if (browser) await browser.close().catch(() => {});
    await killChild(child);
  }
}

main()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error(`SMOKE FAIL: ${e.message}`);
    process.exit(1);
  });
