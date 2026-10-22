/**
 * Browser UAT for user-feedback-v1 - one screenshot per state transition.
 *
 * Walks the exact sequence playwright/chat-feedback.spec.ts asserts
 * (DESIGN.md section 12): send a message, rate it Helpful, reload (persists),
 * change to Not helpful with a reason, reload (persists), retract, reload
 * (persists), then replay the detail request (200 replayed, same
 * feedback_event_id) and probe an unknown message id (404) directly.
 *
 * Playwright MCP is broken in this environment, so this drives
 * playwright-core directly under Node 24 (same pattern as
 * close-product-loop-s1-booking-ui/uat).
 *
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   export E2E_USER_EMAIL=... E2E_USER_PASSWORD=...
 *   cd apps/web and node ../specs/user-feedback-v1/uat/run-uat.mjs
 *
 * Requires the web dev server on UAT_BASE (default :3000) and the API on
 * :8000 with a real LLM key.
 */
import { createRequire } from "node:module";

const req = createRequire(new URL("../../../apps/web/package.json", import.meta.url));
const reqFromTest = createRequire(req.resolve("@playwright/test"));
const pw = reqFromTest("playwright-core");
const chromium = pw.chromium;

const BASE = process.env.UAT_BASE || "http://localhost:3000";
const OUT = new URL("./", import.meta.url).pathname;
const EMAIL = process.env.E2E_USER_EMAIL;
const PASSWORD = process.env.E2E_USER_PASSWORD;
if (!EMAIL || !PASSWORD) throw new Error("set E2E_USER_EMAIL and E2E_USER_PASSWORD in the environment");

const FEEDBACK_PATH = "/api/be/agent/feedback";
function isFeedbackPost(request) {
  return request.method() === "POST" && new URL(request.url()).pathname === FEEDBACK_PATH;
}
function isHistoryGet(url) {
  return /\/api\/be\/agent\/conversations\/[^/]+\/messages$/.test(url.pathname);
}

async function shot(page, name, note) {
  await page.screenshot({ path: OUT + name + ".png", fullPage: true });
  console.log("  captured " + name + ".png -", note);
}

async function reloadHistory(page) {
  const history = page.waitForResponse(function (res) { return isHistoryGet(new URL(res.url())); });
  await page.reload({ waitUntil: "networkidle" });
  const body = await (await history).json();
  await page.getByRole("button", { name: "Open travel assistant" }).click();
  return body.messages;
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
page.setDefaultTimeout(30000);

let messageId = null;
let authHeaders = null;
let detailBody = null;
let detailEventId = null;

try {
  await page.goto(BASE + "/auth/login", { waitUntil: "networkidle" });
  await page.fill("input[name=\"email\"]", EMAIL);
  await page.fill("input[name=\"password\"]", PASSWORD);
  await page.click("button[type=\"submit\"]");
  await page.waitForURL(function (u) { return u.pathname.indexOf("/auth/login") !== 0; }, { timeout: 30000 });
  console.log("signed in as", EMAIL);

  await page.goto(BASE + "/trips", { waitUntil: "networkidle" });
  await shot(page, "01-signed-in", "signed in, on /trips");

  await page.getByRole("button", { name: "Open travel assistant" }).click();
  const chat = page.getByRole("dialog", { name: "Travel Assistant" });
  await chat.getByLabel("Message the travel assistant").waitFor();
  await shot(page, "02-chat-opened", "assistant panel open, composer ready");

  const stream = page.waitForResponse(function (res) { return new URL(res.url()).pathname.endsWith("/agent/stream"); });
  await chat.getByLabel("Message the travel assistant").fill("Reply with one short sentence: what is the capital of Vietnam?");
  await chat.getByRole("button", { name: "Send message" }).click();
  const sse = await (await stream).text();
  const sseMatch = /"assistant_message_id":\s*"([^"]+)"/.exec(sse);
  messageId = sseMatch ? sseMatch[1] : null;
  console.log("assistant_message_id:", messageId);
  if (!messageId) {
    throw new Error("SSE done did not carry assistant_message_id");
  }

  let feedback = chat.getByRole("group", { name: "Rate this answer" }).last();
  let helpful = feedback.getByRole("button", { name: "Helpful", exact: true });
  let notHelpful = feedback.getByRole("button", { name: "Not helpful", exact: true });
  await helpful.waitFor();
  await shot(page, "03-reply-unrated", "reply rendered with Helpful / Not helpful, unrated");

  let messages = await reloadHistory(page);
  const foundAfterFirstReload = messages.some(function (m) { return m.id === messageId; });
  if (!foundAfterFirstReload) {
    throw new Error("history does not contain the message id");
  }
  console.log("history round-trip: message id present after reload");

  const firstPost = page.waitForRequest(isFeedbackPost);
  await helpful.click();
  const firstReq = await firstPost;
  authHeaders = { authorization: firstReq.headers().authorization };
  await page.getByText("Feedback saved").waitFor();
  await shot(page, "04-helpful-saved", "Helpful pressed, live status announces Feedback saved");

  messages = await reloadHistory(page);
  feedback = chat.getByRole("group", { name: "Rate this answer" }).last();
  helpful = feedback.getByRole("button", { name: "Helpful", exact: true });
  notHelpful = feedback.getByRole("button", { name: "Not helpful", exact: true });
  await helpful.waitFor();
  await shot(page, "05-helpful-persists-after-reload", "Helpful still pressed after a reload");

  await notHelpful.click();
  await shot(page, "06-not-helpful-tell-us-more", "switched to Not helpful; Tell us more affordance appears");

  await feedback.getByRole("button", { name: "Tell us more" }).click();
  const dialog = page.getByRole("dialog", { name: "What went wrong?" });
  await dialog.getByRole("radio", { name: "Incomplete answer" }).check();
  await shot(page, "07-reason-dialog", "reason dialog open, Incomplete answer selected");

  const detailResponse = page.waitForResponse(function (res) {
    if (!isFeedbackPost(res.request())) {
      return false;
    }
    const body = res.request().postDataJSON();
    return body && body.action === "add_detail";
  });
  await dialog.getByRole("button", { name: "Save feedback" }).click();
  const detailRes = await detailResponse;
  detailBody = detailRes.request().postData();
  const detailJson = await detailRes.json();
  detailEventId = detailJson.feedback_event_id;
  console.log("detail feedback_event_id:", detailEventId);
  await shot(page, "08-detail-saved", "dialog closed, Not helpful pressed, Tell us more gone");

  messages = await reloadHistory(page);
  const afterDetailEntry = messages.find(function (m) { return m.id === messageId; });
  const afterDetail = afterDetailEntry ? afterDetailEntry.feedback : undefined;
  console.log("effective state after reload:", JSON.stringify(afterDetail));
  const detailOk = afterDetail && afterDetail.rating === "not_helpful" && afterDetail.reason_code === "incomplete";
  if (!detailOk) {
    throw new Error("effective feedback after reload did not match not_helpful/incomplete");
  }
  await shot(page, "09-detail-persists-after-reload", "reload keeps Not helpful + reason, no Tell us more");

  feedback = chat.getByRole("group", { name: "Rate this answer" }).last();
  notHelpful = feedback.getByRole("button", { name: "Not helpful", exact: true });
  await notHelpful.click();
  await page.getByText("Feedback removed").waitFor();
  await shot(page, "10-retracted", "retracted, neither thumb selected");

  messages = await reloadHistory(page);
  const afterRetractEntry = messages.find(function (m) { return m.id === messageId; });
  const afterRetract = (afterRetractEntry && afterRetractEntry.feedback) || null;
  console.log("effective state after retract + reload:", JSON.stringify(afterRetract));
  if (afterRetract !== null) {
    throw new Error("feedback should be null after retract");
  }
  await shot(page, "11-retract-persists-after-reload", "reload confirms neither thumb selected");

  const replay = await page.request.post(BASE + FEEDBACK_PATH, {
    headers: Object.assign({}, authHeaders, { "content-type": "application/json" }),
    data: detailBody,
  });
  const replayBody = await replay.json();
  console.log("replay status:", replay.status(), "body:", JSON.stringify(replayBody));
  const replayOk = replay.status() === 200 && replayBody.replayed === true && replayBody.feedback_event_id === detailEventId;
  if (!replayOk) {
    throw new Error("replay did not return 200 replayed:true with the same feedback_event_id");
  }

  const probe = await page.request.post(BASE + FEEDBACK_PATH, {
    headers: Object.assign({}, authHeaders, { "content-type": "application/json" }),
    data: {
      client_event_id: crypto.randomUUID(),
      assistant_message_id: crypto.randomUUID(),
      action: "set_rating",
      rating: "helpful",
      locale: "en",
    },
  });
  console.log("probe (unknown message id) status:", probe.status());
  if (probe.status() !== 404) {
    throw new Error("probe of an unknown message id did not return 404");
  }

  console.log("ALL CHECKS PASSED - screenshots written to", OUT);
} catch (err) {
  try {
    await page.screenshot({ path: OUT + "zz-failure.png", fullPage: true });
  } catch (shotErr) {
    console.log("could not capture failure screenshot");
  }
  console.log("FAILED -", err.message.split("\n")[0]);
  throw err;
} finally {
  await browser.close();
}
