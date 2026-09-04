import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// --- mock the hook's collaborators ---------------------------------------
vi.mock("next-intl", () => ({ useTranslations: () => (k: string) => k }));
vi.mock("@/lib/identity/useUserId", () => ({
  useIdentity: () => ({ userId: "u1", status: "signed-in" }),
}));
vi.mock("@/lib/api/client", () => ({ streamBaseUrl: () => "" }));

// Hoisted mock fns so per-test overrides drive the hydrate effect.
const h = vi.hoisted(() => ({
  fetchConvo: vi.fn(),
  fetchClaim: vi.fn(),
}));

vi.mock("@/lib/query/agent", () => {
  // A local ClaimError mirroring the real one; the hook imports THIS class, so
  // `instanceof ClaimError` in the hook matches instances the test constructs.
  class ClaimError extends Error {
    status: number;
    constructor(status: number, message?: string) {
      super(message ?? `fetchClaim: ${status}`);
      this.name = "ClaimError";
      this.status = status;
    }
  }
  return {
    ClaimError,
    fetchConversationMessages: h.fetchConvo,
    fetchClaim: h.fetchClaim,
  };
});

import { ClaimError } from "@/lib/query/agent";
import { useAgentStream } from "./useAgentStream";

const CONVERSATION_STORAGE_KEY = "travel.conversationId";
const LEGACY_ANON_STORAGE_KEY = "travel.userId";

const sse = (event: string, data: Record<string, unknown>) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

/** A ReadableStream that emits each frame as a separate async read. */
function wireStream(frames: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (i < frames.length) {
        await new Promise((r) => setTimeout(r, 0));
        controller.enqueue(enc.encode(frames[i++]));
      } else {
        controller.close();
      }
    },
  });
}

const msg = (id: string, role: "user" | "assistant", content: string) => ({
  id,
  conversation_id: "c1",
  role,
  content,
  tool_calls: null,
  created_at: "2026-01-01T00:00:00Z",
});

describe("useAgentStream — interrupt rehydration", () => {
  beforeEach(() => {
    localStorage.clear();
    h.fetchConvo.mockReset();
    h.fetchClaim.mockReset();
    // No legacy anon id in these cases → claim is skipped entirely.
    localStorage.setItem(CONVERSATION_STORAGE_KEY, "c1");
  });

  it("targets the trailing assistant bubble when one exists", async () => {
    h.fetchConvo.mockResolvedValue({
      messages: [msg("m-user", "user", "hi"), msg("a1", "assistant", "draft")],
      interrupt_pending: true,
      interrupt_payload: { type: "plan_approval", draft: "draft" },
    });
    // resume() continuation streams into whichever bubble hydration targeted.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("token", { content: " done" }),
          sse("done", { conversation_id: "c1", current_flow: "planner" }),
        ]),
      })),
    );

    const { result } = renderHook(() => useAgentStream());

    // The pending interrupt is rehydrated from persisted history.
    await waitFor(() => expect(result.current.interrupt).not.toBeNull());
    expect(result.current.interrupt?.conversationId).toBe("c1");

    act(() => {
      result.current.resume(true);
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    // The continuation appended into the EXISTING trailing assistant bubble.
    await waitFor(() =>
      expect(result.current.messages.find((m) => m.id === "a1")?.content).toBe(
        "draft done",
      ),
    );
    expect(result.current.error).toBeNull();
  });

  it("adds a fresh assistant bubble when the last turn is a user turn", async () => {
    h.fetchConvo.mockResolvedValue({
      messages: [msg("m-user", "user", "plan a trip")],
      interrupt_pending: true,
      interrupt_payload: { type: "plan_approval", draft: "" },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("token", { content: "answer" }),
          sse("done", { conversation_id: "c1", current_flow: "planner" }),
        ]),
      })),
    );

    const { result } = renderHook(() => useAgentStream());

    await waitFor(() => expect(result.current.interrupt).not.toBeNull());
    // A fresh empty assistant bubble was appended for the resumed continuation.
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1]?.role).toBe("assistant");

    act(() => {
      result.current.resume(true);
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(false));

    // resume() streamed into that fresh bubble (the last, assistant message).
    await waitFor(() => {
      const last = result.current.messages[result.current.messages.length - 1];
      expect(last?.role).toBe("assistant");
      expect(last?.content).toBe("answer");
    });
    expect(result.current.error).toBeNull();
  });
});

describe("useAgentStream — claim behavior", () => {
  beforeEach(() => {
    localStorage.clear();
    h.fetchConvo.mockReset();
    h.fetchClaim.mockReset();
    // A legacy anon id triggers the one-shot claim on mount.
    localStorage.setItem(LEGACY_ANON_STORAGE_KEY, "anon-1");
    // A stored conversation id lets the hydrate step run (proves it is reached).
    localStorage.setItem(CONVERSATION_STORAGE_KEY, "c1");
    h.fetchConvo.mockResolvedValue({
      messages: [],
      interrupt_pending: false,
      interrupt_payload: null,
    });
  });

  it("keeps the legacy key and surfaces an error on a non-403 claim failure, then still hydrates", async () => {
    h.fetchClaim.mockRejectedValue(new ClaimError(500));

    const { result } = renderHook(() => useAgentStream());

    // The claim failed non-403 → soft error, key preserved for a later retry.
    await waitFor(() =>
      expect(result.current.error).toBe("errorClaimFailed"),
    );
    expect(localStorage.getItem(LEGACY_ANON_STORAGE_KEY)).toBe("anon-1");
    // Hydration was NOT skipped by the claim failure (bare-return bug guard).
    await waitFor(() =>
      expect(h.fetchConvo).toHaveBeenCalledWith("c1", "u1"),
    );
  });

  it("clears the legacy key on a 403 claim, with no error, then still hydrates", async () => {
    h.fetchClaim.mockRejectedValue(new ClaimError(403));

    const { result } = renderHook(() => useAgentStream());

    // 403 = nothing to claim → drop the one-shot key, no user-facing error.
    await waitFor(() =>
      expect(h.fetchConvo).toHaveBeenCalledWith("c1", "u1"),
    );
    expect(localStorage.getItem(LEGACY_ANON_STORAGE_KEY)).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
