import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// --- mock the hook's collaborators (real research parser stays live) --------
vi.mock("@/lib/api/client", () => ({ streamBaseUrl: () => "" }));
vi.mock("@/lib/supabase/authHeader", () => ({ authHeader: async () => ({}) }));

import { useResearchStream } from "./useResearchStream";

/** A ReadableStream that emits each frame as a SEPARATE async read (like a real wire). */
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

/** A stream fed one frame at a time, so a test can assert state after each event. */
function controllableStream() {
  const enc = new TextEncoder();
  let ctrl: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      ctrl = c;
    },
  });
  return {
    stream,
    push: (frame: string) => ctrl.enqueue(enc.encode(frame)),
    close: () => ctrl.close(),
  };
}

/** A stream that opens but never closes — lets a test observe abort on unmount. */
function pendingStream(): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    pull() {
      return new Promise<void>(() => {
        /* never resolves */
      });
    },
  });
}

const sse = (event: string, data: Record<string, unknown>) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

const FULL_RUN = [
  sse("research_start", { run_id: "r1", trip_id: "t1" }),
  sse("research_phase", {
    todos: [
      { content: "Scope the trip", status: "in_progress" },
      { content: "Draft dossier", status: "pending" },
    ],
  }),
  sse("research_subagent", { name: "flights", status: "running" }),
  sse("research_tool", { name: "search_flights", status: "running" }),
  sse("research_file", { path: "flights.md", bytes: 1024 }),
  sse("research_eval", { iteration: 1, result: "pass", explanation: "looks solid" }),
  sse("research_done", { status: "completed", files: ["flights.md", "summary.md"], proposal_ready: true }),
];

describe("useResearchStream — reduction", () => {
  it("reduces the projected events into render state after each one", async () => {
    // Feed one frame at a time so each event's reduction is observed in
    // isolation before the next arrives (a self-completing stream would race
    // the terminal event past the intermediate assertions).
    const wire = controllableStream();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, body: wire.stream })));

    const { result } = renderHook(() => useResearchStream("r1"));

    // start — tripId confirms the start event landed (runId is pinned
    // synchronously at open, tripId only by the event).
    act(() => wire.push(FULL_RUN[0]));
    await waitFor(() => expect(result.current.tripId).toBe("t1"));
    expect(result.current.runId).toBe("r1");
    expect(result.current.status).toBe("streaming");

    // phase
    act(() => wire.push(FULL_RUN[1]));
    await waitFor(() => expect(result.current.todos).toHaveLength(2));
    expect(result.current.todos[0]).toEqual({
      content: "Scope the trip",
      status: "in_progress",
    });

    // subagent
    act(() => wire.push(FULL_RUN[2]));
    await waitFor(() => expect(result.current.subagents).toHaveLength(1));
    expect(result.current.subagents[0]).toEqual({ name: "flights", status: "running" });

    // tool
    act(() => wire.push(FULL_RUN[3]));
    await waitFor(() => expect(result.current.tools).toHaveLength(1));
    expect(result.current.tools[0]).toEqual({ name: "search_flights", status: "running" });

    // file
    act(() => wire.push(FULL_RUN[4]));
    await waitFor(() => expect(result.current.files).toHaveLength(1));
    expect(result.current.files[0]).toEqual({ path: "flights.md", bytes: 1024 });

    // eval
    act(() => wire.push(FULL_RUN[5]));
    await waitFor(() => expect(result.current.lastEval).not.toBeNull());
    expect(result.current.lastEval).toEqual({
      iteration: 1,
      result: "pass",
      explanation: "looks solid",
    });

    // terminal done — status flips, proposal flag set, terminal files merged in
    act(() => {
      wire.push(FULL_RUN[6]);
      wire.close();
    });
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.proposalReady).toBe(true);
    expect(result.current.files.map((f) => f.path)).toEqual(["flights.md", "summary.md"]);
    // The streamed file keeps its byte size; the merge-only file defaults to 0.
    expect(result.current.files).toContainEqual({ path: "flights.md", bytes: 1024 });
    expect(result.current.files).toContainEqual({ path: "summary.md", bytes: 0 });
    expect(result.current.error).toBeNull();
  });

  it("upserts subagent/tool status by name instead of duplicating", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("research_start", { run_id: "r1", trip_id: "t1" }),
          sse("research_subagent", { name: "flights", status: "running" }),
          sse("research_tool", { name: "search_flights", status: "running" }),
          sse("research_tool", { name: "search_flights", status: "ok" }),
          sse("research_subagent", { name: "flights", status: "done" }),
          sse("research_done", { status: "completed", files: [], proposal_ready: false }),
        ]),
      })),
    );

    const { result } = renderHook(() => useResearchStream("r1"));
    await waitFor(() => expect(result.current.status).toBe("done"));

    expect(result.current.subagents).toEqual([{ name: "flights", status: "done" }]);
    expect(result.current.tools).toEqual([{ name: "search_flights", status: "ok" }]);
    expect(result.current.proposalReady).toBe(false);
  });

  it("surfaces a terminal research_error as error state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([
          sse("research_start", { run_id: "r1", trip_id: "t1" }),
          sse("research_error", { code: "provider_down", message: "upstream failed" }),
        ]),
      })),
    );

    const { result } = renderHook(() => useResearchStream("r1"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error).toEqual({
      code: "provider_down",
      message: "upstream failed",
    });
  });

  it("marks the stream errored when it drops before a terminal event", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        body: wireStream([sse("research_start", { run_id: "r1", trip_id: "t1" })]),
      })),
    );

    const { result } = renderHook(() => useResearchStream("r1"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error?.code).toBe("stream");
  });
});

describe("useResearchStream — lifecycle", () => {
  it("holds idle and opens no stream when runId is null", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, body: wireStream(FULL_RUN) }));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useResearchStream(null));
    expect(result.current.status).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("aborts the in-flight stream on unmount", async () => {
    let captured: AbortSignal | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        captured = init.signal ?? null;
        return { ok: true, body: pendingStream() };
      }),
    );

    const { result, unmount } = renderHook(() => useResearchStream("r1"));
    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured!.aborted).toBe(false);
    // While the stream is open (never terminal), the hook stays "streaming".
    expect(result.current.status).toBe("streaming");

    unmount();
    expect(captured!.aborted).toBe(true);
  });

  it("resets state and re-subscribes when runId changes", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        body: wireStream([
          sse("research_start", { run_id: "r1", trip_id: "t1" }),
          sse("research_file", { path: "a.md", bytes: 10 }),
          sse("research_done", { status: "completed", files: ["a.md"], proposal_ready: true }),
        ]),
      })
      .mockResolvedValueOnce({
        ok: true,
        body: wireStream([
          sse("research_start", { run_id: "r2", trip_id: "t2" }),
          sse("research_file", { path: "b.md", bytes: 20 }),
          sse("research_done", { status: "completed", files: ["b.md"], proposal_ready: false }),
        ]),
      });
    vi.stubGlobal("fetch", fetchMock);

    const { result, rerender } = renderHook(
      ({ runId }: { runId: string | null }) => useResearchStream(runId),
      { initialProps: { runId: "r1" } },
    );

    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.runId).toBe("r1");
    expect(result.current.files.map((f) => f.path)).toEqual(["a.md"]);

    rerender({ runId: "r2" });

    // The previous run's files must not bleed into the new run.
    await waitFor(() => expect(result.current.runId).toBe("r2"));
    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.tripId).toBe("t2");
    expect(result.current.files.map((f) => f.path)).toEqual(["b.md"]);
    expect(result.current.proposalReady).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
