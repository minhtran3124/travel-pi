import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ResearchRunSummary } from "@/lib/api/research";

const api = vi.hoisted(() => ({ getLatestResearch: vi.fn() }));
vi.mock("@/lib/api/research", () => api);

import { RESEARCH_POLL_MS, useResearchWatch } from "./useResearchWatch";

function run(status: string, runId = "run-1"): ResearchRunSummary {
  return {
    run_id: runId,
    trip_id: "trip-1",
    status,
    thread_turn: 1,
    files: ["flights.md"],
    proposal_ready: true,
  };
}

/** Let the pending read resolve and React apply its state update. */
async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("useResearchWatch", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    api.getLatestResearch.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("raises done when a run it saw running completes", async () => {
    api.getLatestResearch
      .mockResolvedValueOnce(run("running"))
      .mockResolvedValueOnce(run("completed"));
    const { result } = renderHook(() => useResearchWatch("trip-1", true));
    await flush();
    expect(result.current.done).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(RESEARCH_POLL_MS);
    });

    expect(result.current.done?.run_id).toBe("run-1");
    expect(api.getLatestResearch).toHaveBeenCalledTimes(2);
  });

  it("never raises done for a run that was already completed", async () => {
    api.getLatestResearch.mockResolvedValue(run("completed"));
    const { result } = renderHook(() => useResearchWatch("trip-1", true));
    await flush();
    act(() => result.current.check());
    await flush();

    expect(result.current.done).toBeNull();
  });

  it("exposes the latest completed run from the mount check, without done", async () => {
    api.getLatestResearch.mockResolvedValue(run("completed"));
    const { result } = renderHook(() => useResearchWatch("trip-1", true));
    await flush();

    expect(result.current.completed?.run_id).toBe("run-1");
    expect(result.current.done).toBeNull();
  });

  it("exposes completed when a followed run finishes", async () => {
    api.getLatestResearch
      .mockResolvedValueOnce(run("running"))
      .mockResolvedValueOnce(run("completed"));
    const { result } = renderHook(() => useResearchWatch("trip-1", true));
    await flush();
    expect(result.current.completed).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(RESEARCH_POLL_MS);
    });

    expect(result.current.completed?.run_id).toBe("run-1");
    expect(result.current.done?.run_id).toBe("run-1");
  });

  it("does not raise done when the run fails", async () => {
    api.getLatestResearch
      .mockResolvedValueOnce(run("running"))
      .mockResolvedValueOnce(run("failed"));
    const { result } = renderHook(() => useResearchWatch("trip-1", true));
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RESEARCH_POLL_MS);
    });

    expect(result.current.done).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RESEARCH_POLL_MS * 3);
    });
    expect(api.getLatestResearch).toHaveBeenCalledTimes(2);
  });

  it("check() after a research turn starts following a new run", async () => {
    api.getLatestResearch.mockRejectedValueOnce(new Error("404"));
    const { result } = renderHook(() => useResearchWatch("trip-1", true));
    await flush();

    api.getLatestResearch
      .mockResolvedValueOnce(run("running", "run-2"))
      .mockResolvedValueOnce(run("completed", "run-2"));
    act(() => result.current.check());
    await flush();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RESEARCH_POLL_MS);
    });

    expect(result.current.done?.run_id).toBe("run-2");
    act(() => result.current.dismiss());
    expect(result.current.done).toBeNull();
  });

  it("check() while already following does not start a second poll chain", async () => {
    api.getLatestResearch.mockResolvedValue(run("running"));
    const { result } = renderHook(() => useResearchWatch("trip-1", true));
    await flush();
    act(() => result.current.check());
    act(() => result.current.check());
    await flush();

    expect(api.getLatestResearch).toHaveBeenCalledTimes(1);
  });

  it("does nothing when disabled or off a trip page", async () => {
    renderHook(() => useResearchWatch("trip-1", false));
    renderHook(() => useResearchWatch(undefined, true));
    await flush();

    expect(api.getLatestResearch).not.toHaveBeenCalled();
  });

  it("stops polling on unmount", async () => {
    api.getLatestResearch.mockResolvedValue(run("running"));
    const { unmount } = renderHook(() => useResearchWatch("trip-1", true));
    await flush();
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RESEARCH_POLL_MS * 3);
    });

    expect(api.getLatestResearch).toHaveBeenCalledTimes(1);
  });
});
