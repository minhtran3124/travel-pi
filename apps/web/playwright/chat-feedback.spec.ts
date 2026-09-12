/**
 * Chat feedback end-to-end — DESIGN.md §12 (specs/user-feedback-v1): send a
 * message, rate the reply, and prove the rating survives a reload at every
 * transition (helpful → not helpful + reason → retracted), then replay a
 * request and probe another user's id through the same endpoint.
 *
 * Runs already signed in like `trip-smoke.spec.ts` (the `setup` project saves
 * the session; the chromium project reuses it via `storageState`).
 *
 * Opt-in / local only, and stricter than the other smokes: it needs a backend
 * on :8000 with a REAL LLM key. Without one every chat turn takes the failure
 * path — the fallback reply is persisted but its run is `failed`, so it is not
 * rateable and the feedback controls are hidden by design (DESIGN §7.1). CI's
 * web-e2e job starts the backend with `OPENAI_API_KEY=""`, so this spec skips
 * unless `E2E_CHAT_LLM=1` declares such a backend:
 *
 *   # from repo root — backend on :8000 with apps/api/.env holding a real key
 *   (cd apps/api && ../../.venv/bin/uvicorn app.main:app --port 8000)
 *
 *   # from apps/web
 *   export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH"
 *   E2E_CHAT_LLM=1 pnpm e2e playwright/chat-feedback.spec.ts
 */
import { expect, test, type Page, type Request } from "@playwright/test";

import { hasCreds } from "./e2e-env";

test.skip(
  !hasCreds || process.env.E2E_CHAT_LLM !== "1",
  "needs E2E creds and E2E_CHAT_LLM=1 (a backend with a real LLM key)",
);

const FEEDBACK_PATH = "/api/be/agent/feedback";

const isFeedbackPost = (req: Request) =>
  req.method() === "POST" && new URL(req.url()).pathname === FEEDBACK_PATH;

/** The history GET the widget issues on (re)load. */
const isHistoryGet = (url: URL) =>
  /\/api\/be\/agent\/conversations\/[^/]+\/messages$/.test(url.pathname);

/** Reload and return the persisted history the widget re-renders from. */
async function reloadHistory(page: Page) {
  const history = page.waitForResponse((res) => isHistoryGet(new URL(res.url())));
  await page.reload();
  const body = (await (await history).json()) as {
    messages: {
      id: string;
      feedback?: { rating: string; reason_code?: string | null } | null;
    }[];
  };
  await page.getByRole("button", { name: "Open travel assistant" }).click();
  return body.messages;
}

test("rate a reply, keep the rating across reloads, replay and probe", async ({
  page,
}) => {
  await page.goto("/trips");
  await page.getByRole("button", { name: "Open travel assistant" }).click();
  const chat = page.getByRole("dialog", { name: "Travel Assistant" });

  // 1. Send a message; capture the server message id from the SSE `done`.
  const stream = page.waitForResponse((res) =>
    new URL(res.url()).pathname.endsWith("/agent/stream"),
  );
  await chat
    .getByLabel("Message the travel assistant")
    .fill("Reply with one short sentence: what is the capital of Vietnam?");
  await chat.getByRole("button", { name: "Send message" }).click();
  // `text()` resolves once the stream closes, i.e. after `event: done`.
  const sse = await (await stream).text();
  const messageId = /"assistant_message_id":\s*"([^"]+)"/.exec(sse)?.[1];
  expect(messageId, "SSE done carries assistant_message_id").toBeTruthy();

  const feedback = chat.getByRole("group", { name: "Rate this answer" }).last();
  const helpful = feedback.getByRole("button", { name: "Helpful" });
  const notHelpful = feedback.getByRole("button", { name: "Not helpful" });
  await expect(helpful).toBeVisible();

  // 2. Reload; history names the same message id.
  let messages = await reloadHistory(page);
  expect(messages.map((m) => m.id)).toContain(messageId);

  // 3. Rate helpful; reload; the pressed state remains.
  const firstPost = page.waitForRequest(isFeedbackPost);
  await helpful.click();
  const authHeaders = { authorization: (await firstPost).headers().authorization };
  await expect(helpful).toHaveAttribute("aria-pressed", "true");
  messages = await reloadHistory(page);
  await expect(helpful).toHaveAttribute("aria-pressed", "true");

  // 4. Change to not helpful with a reason; reload; state and detail remain.
  await notHelpful.click();
  await expect(notHelpful).toHaveAttribute("aria-pressed", "true");
  await feedback.getByRole("button", { name: "Tell us more" }).click();
  const dialog = page.getByRole("dialog", { name: "What went wrong?" });
  await dialog.getByRole("radio", { name: "Incomplete answer" }).check();
  const detailPost = page.waitForRequest(isFeedbackPost);
  await dialog.getByRole("button", { name: "Save feedback" }).click();
  const detailBody = (await detailPost).postData()!;
  await expect(dialog).toBeHidden();
  messages = await reloadHistory(page);
  await expect(notHelpful).toHaveAttribute("aria-pressed", "true");
  expect(messages.find((m) => m.id === messageId)?.feedback).toMatchObject({
    rating: "not_helpful",
    reason_code: "incomplete",
  });
  await expect(feedback.getByRole("button", { name: "Tell us more" })).toHaveCount(0);

  // 5. Retract; reload; neither thumb is selected.
  await notHelpful.click();
  await expect(notHelpful).toHaveAttribute("aria-pressed", "false");
  messages = await reloadHistory(page);
  await expect(helpful).toHaveAttribute("aria-pressed", "false");
  await expect(notHelpful).toHaveAttribute("aria-pressed", "false");
  expect(messages.find((m) => m.id === messageId)?.feedback ?? null).toBeNull();

  // 6. Replay the detail request verbatim: 200 `replayed`, state unchanged.
  const replay = await page.request.post(FEEDBACK_PATH, {
    headers: { ...authHeaders, "content-type": "application/json" },
    data: detailBody,
  });
  expect(replay.status()).toBe(200);
  expect(await replay.json()).toMatchObject({ replayed: true });
  messages = await reloadHistory(page);
  expect(messages.find((m) => m.id === messageId)?.feedback ?? null).toBeNull();

  // 7. Another user's (unknown) id: the same non-enumerating 404.
  const probe = await page.request.post(FEEDBACK_PATH, {
    headers: { ...authHeaders, "content-type": "application/json" },
    data: {
      client_event_id: crypto.randomUUID(),
      assistant_message_id: crypto.randomUUID(),
      action: "set_rating",
      rating: "helpful",
      locale: "en",
    },
  });
  expect(probe.status()).toBe(404);
});
