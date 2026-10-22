import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// --- mock the hook's collaborators ---------------------------------------
vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("@/lib/identity/useUserId", () => ({
  useIdentity: () => ({ userId: "u1", status: "signed-in" }),
}));
vi.mock("@/lib/api/client", () => ({ streamBaseUrl: () => "" }));
vi.mock("@/lib/query/agent", () => ({
  // No legacy anon id / stored conversation is seeded in these tests, so claim
  // and hydration both short-circuit; provide the new object shape regardless.
  fetchClaim: async () => ({ claimed: 0 }),
  fetchConversationMessages: async () => ({
    messages: [],
    interrupt_pending: false,
    interrupt_payload: null,
  }),
}));

import { useAgentStream } from "./useAgentStream";

const sse = (event: string, data: Record<string, unknown>) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

/**
 * A ReadableStream that emits its frames, then blocks until `signal` aborts and
 * errors the stream — mirroring how a real `fetch(..., { signal })` body rejects
 * its reader on abort. This lets the test drive a genuinely in-flight turn and
 * then interrupt it via `stop()`.
 */
function abortableStream(
  frames: string[],
  signal: AbortSignal,
): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (i < frames.length) {
        await new Promise((r) => setTimeout(r, 0));
        controller.enqueue(enc.encode(frames[i++]));
        return;
      }
      // No more frames: hang until the caller aborts, then error the stream so
      // the hook's `for await` throws (AbortError) and its finally-block runs.
      await new Promise<never>((_resolve, reject) => {
        const fail = () =>
          reject(new DOMException("Aborted", "AbortError"));
        if (signal.aborted) return fail();
        signal.addEventListener("abort", fail, { once: true });
      });
    },
  });
}

describe("useAgentStream — user Stop", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("stops an in-flight stream: isStreaming resets to false with no error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => ({
        ok: true,
        body: abortableStream(
          [
            sse("start", { conversation_id: "c1" }),
            sse("token", { content: "Thinking" }),
          ],
          init.signal as AbortSignal,
        ),
      })),
    );

    const { result } = renderHook(() => useAgentStream());

    act(() => {
      result.current.send("plan a long trip");
    });

    // The turn is genuinely in flight (stream is emitting, not yet closed).
    await waitFor(() => expect(result.current.isStreaming).toBe(true));
    // isStreaming flips true synchronously in send(), before the "token" event
    // has necessarily been read off the wire — wait for the reveal buffer to
    // have actually started draining the token before stopping, so this test
    // exercises "unrevealed text still buffered", not a race against an event
    // that hasn't arrived yet.
    await waitFor(() =>
      expect(result.current.messages.at(-1)?.content.length).toBeGreaterThan(0),
    );

    act(() => {
      result.current.stop();
    });

    // A deliberate Stop still runs the finally-block: streaming resets and no
    // error surfaces (the abort is not treated as a stream failure).
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.error).toBeNull();

    // The typewriter reveal buffer drains on its own rAF loop, independent of
    // the abort signal, so stop() must flush it — otherwise the already-sent
    // "Thinking" token could still be mid-reveal (or entirely unrevealed) even
    // though isStreaming has already reset to false.
    //
    // A deliberate Stop also appends a small "stopped" note to whatever content
    // had already streamed in, so the bubble never renders empty/unexplained.
    const assistant = result.current.messages.at(-1);
    expect(assistant?.content).toBe("Thinking\n\nstoppedSuffix");
  });

  it("a Stop that lands after `done` drops the persisted id — stopped content is not rateable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => ({
        ok: true,
        body: abortableStream(
          [
            sse("start", { conversation_id: "c1" }),
            sse("token", { content: "Thinking" }),
            sse("done", {
              conversation_id: "c1",
              current_flow: "concierge",
              assistant_message_id: "srv-1",
            }),
          ],
          init.signal as AbortSignal,
        ),
      })),
    );

    const { result } = renderHook(() => useAgentStream());
    act(() => {
      result.current.send("plan a long trip");
    });

    // `done` was read off the wire (id recorded) while the body is still open.
    await waitFor(() =>
      expect(result.current.messages.at(-1)?.serverMessageId).toBe("srv-1"),
    );

    act(() => {
      result.current.stop();
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    const assistant = result.current.messages.at(-1);
    expect(assistant?.content).toBe("Thinking\n\nstoppedSuffix");
    // The bubble no longer matches the persisted row → not rateable.
    expect(assistant?.serverMessageId).toBeUndefined();
  });

  it("stops before any token arrives: shows a friendly stopped placeholder", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => ({
        ok: true,
        body: abortableStream(
          [sse("start", { conversation_id: "c1" })],
          init.signal as AbortSignal,
        ),
      })),
    );

    const { result } = renderHook(() => useAgentStream());

    act(() => {
      result.current.send("plan a long trip");
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(true));

    act(() => {
      result.current.stop();
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.error).toBeNull();

    const assistant = result.current.messages.at(-1);
    expect(assistant?.content).toBe("stoppedEmpty");
  });
});
