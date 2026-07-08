import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

// --- mock the hook's collaborators ---------------------------------------
vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("@/lib/identity/useUserId", () => ({ useUserId: () => "u1" }));
vi.mock("@/lib/api/client", () => ({ streamBaseUrl: () => "" }));
const chatFallback = vi.fn();
vi.mock("@/lib/query/agent", () => ({
  chatFallback: (b: unknown) => chatFallback(b),
  // Hydration-on-mount calls this; resolve empty so the live-stream assertions
  // below run against a clean slate (no persisted history to replay).
  fetchConversationMessages: async () => [],
}));

import { useAgentStream } from "./useAgentStream";

/** A ReadableStream that emits each frame as a SEPARATE async read (like a real wire). */
function wireStream(frames: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (i < frames.length) {
        // Defer to a macrotask so React can flush a render between frames.
        await new Promise((r) => setTimeout(r, 0));
        controller.enqueue(enc.encode(frames[i++]));
      } else {
        controller.close();
      }
    },
  });
}

const sse = (event: string, data: Record<string, unknown>) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

describe("useAgentStream — live token accumulation", () => {
  beforeEach(() => {
    chatFallback.mockReset();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("subagent", { name: "concierge" }),
          sse("token", { content: "Visit" }),
          sse("token", { content: " Tokyo" }),
          sse("token", { content: " Tower" }),
          sse("done", { conversation_id: "c1", current_flow: "concierge" }),
        ]),
      })),
    );
  });

  it("accumulates token deltas into the assistant message", async () => {
    const { result } = renderHook(() => useAgentStream());

    act(() => {
      result.current.send("what to see in tokyo?");
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    // Text reveals via a smooth typewriter drip that keeps draining after the
    // wire ends, so wait for the full answer to finish revealing.
    await waitFor(() =>
      expect(
        result.current.messages.find((m) => m.role === "assistant")?.content,
      ).toBe("Visit Tokyo Tower"),
    );
    expect(chatFallback).not.toHaveBeenCalled();
    expect(result.current.error).toBeNull();
  });

  it("ignores a duplicate send fired in the same tick (no double turn)", async () => {
    const { result } = renderHook(() => useAgentStream());

    // Two synchronous sends before isStreaming state commits.
    act(() => {
      result.current.send("hi");
      result.current.send("hi");
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    expect(result.current.messages.filter((m) => m.role === "user")).toHaveLength(1);
    expect(
      result.current.messages.filter((m) => m.role === "assistant"),
    ).toHaveLength(1);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it("ignores subagent/tool events — only the final answer is rendered", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("subagent", { name: "concierge" }),
          sse("tool_call", { id: "t1", name: "get_weather", args_preview: "{}", subagent: "concierge" }),
          sse("token", { content: "Sunny" }),
          sse("tool_result", { id: "t1", status: "ok" }),
          sse("done", { conversation_id: "c1", current_flow: "concierge" }),
        ]),
      })),
    );
    const { result } = renderHook(() => useAgentStream());
    act(() => {
      result.current.send("weather?");
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    // Final answer only — no subagent/tool text leaks into the bubble. Wait for
    // the smooth-reveal drip to finish draining the buffered tokens.
    await waitFor(() =>
      expect(
        result.current.messages.find((m) => m.role === "assistant")?.content,
      ).toBe("Sunny"),
    );
    expect(result.current.error).toBeNull();
  });
});

describe("useAgentStream — follow-up suggestions", () => {
  beforeEach(() => {
    chatFallback.mockReset();
  });

  it("exposes follow-up suggestions carried by the terminal done event", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("token", { content: "Booked" }),
          sse("done", {
            conversation_id: "c1",
            current_flow: "booking",
            suggestions: ["booking.bookThis", "booking.comparePrices"],
          }),
        ]),
      })),
    );

    const { result } = renderHook(() => useAgentStream());

    act(() => {
      result.current.send("book it");
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    await waitFor(() =>
      expect(result.current.suggestions).toEqual([
        "booking.bookThis",
        "booking.comparePrices",
      ]),
    );
  });

  it("clears stale suggestions at the start of the next send", async () => {
    const withSuggestions = () => ({
      ok: true,
      body: wireStream([
        sse("start", { conversation_id: "c1" }),
        sse("token", { content: "Booked" }),
        sse("done", {
          conversation_id: "c1",
          current_flow: "booking",
          suggestions: ["booking.bookThis", "booking.comparePrices"],
        }),
      ]),
    });
    const noSuggestions = () => ({
      ok: true,
      body: wireStream([
        sse("start", { conversation_id: "c1" }),
        sse("token", { content: "Hello" }),
        sse("done", { conversation_id: "c1", current_flow: "concierge", suggestions: [] }),
      ]),
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementationOnce(async () => withSuggestions())
        .mockImplementationOnce(async () => noSuggestions()),
    );

    const { result } = renderHook(() => useAgentStream());

    // First turn populates suggestions.
    act(() => {
      result.current.send("book it");
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    await waitFor(() =>
      expect(result.current.suggestions).toEqual([
        "booking.bookThis",
        "booking.comparePrices",
      ]),
    );

    // A new turn clears the stale chips synchronously at its start.
    act(() => {
      result.current.send("thanks");
    });
    expect(result.current.suggestions).toEqual([]);

    // And they stay cleared when the next turn carries none.
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    await waitFor(() => expect(result.current.suggestions).toEqual([]));
  });
});
