import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

// --- mock the hook's collaborators ---------------------------------------
vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("@/lib/identity/useUserId", () => ({
  useIdentity: () => ({ userId: "u1", status: "signed-in" }),
}));
vi.mock("@/lib/api/client", () => ({ streamBaseUrl: () => "" }));
const chatFallback = vi.fn();
vi.mock("@/lib/query/agent", () => ({
  chatFallback: (b: unknown) => chatFallback(b),
  // Hydration-on-mount calls this; resolve empty so the live-stream assertions
  // below run against a clean slate (no persisted history to replay).
  fetchConversationMessages: async () => ({
    messages: [],
    interrupt_pending: false,
    interrupt_payload: null,
  }),
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

describe("useAgentStream — per-turn activity + panels", () => {
  it("surfaces tool steps and panels onto the streaming assistant message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("subagent", { name: "concierge" }),
          sse("tool_call", { id: "t1", name: "get_weather", args_preview: "{}", subagent: "concierge" }),
          sse("token", { content: "Sunny" }),
          sse("panel", { tool_call_id: "t1", kind: "weather", data: { location_name: "Da Nang" } }),
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

    const assistant = () =>
      result.current.messages.find((m) => m.role === "assistant");

    // One completed step, attributed to the active specialist.
    await waitFor(() => expect(assistant()?.activity).toHaveLength(1));
    expect(assistant()?.activity[0]).toMatchObject({
      id: "t1",
      tool: "get_weather",
      subagent: "concierge",
      status: "ok",
    });

    // Exactly one panel attached to the turn, mirrored in the flat array.
    expect(assistant()?.panels).toHaveLength(1);
    expect(assistant()?.panels[0]?.kind).toBe("weather");
    expect(result.current.panels).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it("upserts a re-emitted panel of the same kind instead of duplicating the card", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("tool_call", { id: "t1", name: "get_weather", args_preview: "{}", subagent: "concierge" }),
          sse("panel", { tool_call_id: "t1", kind: "weather", data: { v: 1 } }),
          // Reflection/revision passes re-run the tool under fresh call ids.
          sse("panel", { tool_call_id: "t2", kind: "weather", data: { v: 2 } }),
          sse("panel", { tool_call_id: "t3", kind: "weather", data: { v: 3 } }),
          sse("tool_result", { id: "t1", status: "ok" }),
          sse("token", { content: "Sunny" }),
          sse("done", { conversation_id: "c1", current_flow: "concierge" }),
        ]),
      })),
    );

    const { result } = renderHook(() => useAgentStream());
    act(() => {
      result.current.send("weather?");
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    const assistant = result.current.messages.find((m) => m.role === "assistant");
    // One card per result kind, carrying the latest payload.
    expect(assistant?.panels).toHaveLength(1);
    expect(assistant?.panels[0]?.data).toEqual({ v: 3 });
  });

  it("keeps a turn's activity across a reset", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("subagent", { name: "concierge" }),
          sse("tool_call", { id: "t1", name: "get_weather", args_preview: "{}", subagent: "concierge" }),
          sse("tool_result", { id: "t1", status: "ok" }),
          sse("token", { content: "Draft" }),
          sse("reset", {}),
          sse("token", { content: "Final" }),
          sse("done", { conversation_id: "c1", current_flow: "concierge" }),
        ]),
      })),
    );

    const { result } = renderHook(() => useAgentStream());
    act(() => {
      result.current.send("weather?");
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    const assistant = () =>
      result.current.messages.find((m) => m.role === "assistant");

    // Reset drops the superseded draft text but keeps the recorded activity.
    await waitFor(() => expect(assistant()?.content).toBe("Final"));
    expect(assistant()?.activity).toHaveLength(1);
    expect(assistant()?.activity[0]?.status).toBe("ok");
  });

  it("stamps elapsedMs on the assistant message when the turn ends", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("token", { content: "Hi" }),
          sse("done", { conversation_id: "c1", current_flow: "concierge" }),
        ]),
      })),
    );

    const { result } = renderHook(() => useAgentStream());
    act(() => {
      result.current.send("hi");
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    const assistant = result.current.messages.find((m) => m.role === "assistant");
    expect(typeof assistant?.elapsedMs).toBe("number");
    expect(assistant?.elapsedMs).toBeGreaterThanOrEqual(0);
  });

  it("regenerate re-runs the question through the rerun loop with retry:true and no duplicate user bubble", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("token", { content: "First answer" }),
          sse("done", { conversation_id: "c1", current_flow: "concierge" }),
        ]),
      })
      // The rerun (shared with retry) must ALSO surface tool events — this
      // covers the non-send event loop the plan names as a regression risk.
      .mockResolvedValueOnce({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("subagent", { name: "concierge" }),
          sse("tool_call", { id: "t9", name: "get_weather", args_preview: "{}", subagent: "concierge" }),
          sse("tool_result", { id: "t9", status: "ok" }),
          sse("token", { content: "Second answer" }),
          sse("done", { conversation_id: "c1", current_flow: "concierge" }),
        ]),
      });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAgentStream());
    act(() => {
      result.current.send("weather?");
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    act(() => {
      result.current.regenerate();
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    // Exactly one user bubble and one assistant bubble survive.
    const users = result.current.messages.filter((m) => m.role === "user");
    const assistants = result.current.messages.filter(
      (m) => m.role === "assistant",
    );
    expect(users).toHaveLength(1);
    expect(assistants).toHaveLength(1);
    // The reveal animation drips characters; wait for the full text.
    await waitFor(() =>
      expect(
        result.current.messages.find((m) => m.role === "assistant")?.content,
      ).toBe("Second answer"),
    );
    // The rerun surfaced the tool step onto the fresh assistant message.
    expect(assistants[0]?.activity).toHaveLength(1);
    expect(assistants[0]?.activity[0]?.status).toBe("ok");
    // The second request went out with retry:true (no re-saved question).
    const secondBody = JSON.parse(fetchMock.mock.calls[1][1].body as string);
    expect(secondBody.retry).toBe(true);
    expect(secondBody.message).toBe("weather?");
  });

  it("surfaces tool events streamed by the resume loop after an interrupt", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("token", { content: "Draft plan" }),
          sse("interrupt", { conversation_id: "c1", payload: { kind: "plan_approval" } }),
        ]),
      })
      .mockResolvedValueOnce({
        ok: true,
        body: wireStream([
          sse("subagent", { name: "planner" }),
          sse("tool_call", { id: "t5", name: "search_hotels", args_preview: "{}", subagent: "planner" }),
          sse("tool_result", { id: "t5", status: "ok" }),
          sse("token", { content: " — booked" }),
          sse("done", { conversation_id: "c1", current_flow: "planner" }),
        ]),
      });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useAgentStream());
    act(() => {
      result.current.send("plan a trip");
    });
    await waitFor(() => expect(result.current.interrupt).not.toBeNull());

    act(() => {
      result.current.resume(true);
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    const assistant = result.current.messages.find((m) => m.role === "assistant");
    // The resume loop appended its tool step to the same assistant turn.
    expect(assistant?.activity.some((step) => step.id === "t5" && step.status === "ok")).toBe(true);
  });
});

describe("useAgentStream — panel language plumbing", () => {
  it("carries `language` from panel/done events into panelLanguage", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("panel", {
            tool_call_id: "t1",
            kind: "weather",
            data: { location_name: "Da Nang" },
            language: "vi",
          }),
          sse("token", { content: "Xin chao" }),
          sse("done", { conversation_id: "c1", current_flow: "concierge", language: "vi" }),
        ]),
      })),
    );

    const { result } = renderHook(() => useAgentStream());
    act(() => {
      result.current.send("thoi tiet da nang?");
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    expect(result.current.panelLanguage).toBe("vi");
    // The accumulated panel artifact carries the same language.
    expect(result.current.panels[0]?.language).toBe("vi");
    expect(result.current.error).toBeNull();
  });

  it("leaves panelLanguage at the default 'en' when events omit `language`", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("start", { conversation_id: "c1" }),
          sse("panel", { tool_call_id: "t1", kind: "weather", data: {} }),
          sse("token", { content: "Sunny" }),
          sse("done", { conversation_id: "c1", current_flow: "concierge" }),
        ]),
      })),
    );

    const { result } = renderHook(() => useAgentStream());
    // Default before any turn.
    expect(result.current.panelLanguage).toBe("en");

    act(() => {
      result.current.send("weather?");
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    expect(result.current.panelLanguage).toBe("en");
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
