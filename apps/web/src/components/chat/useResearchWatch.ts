"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getLatestResearch, type ResearchRunSummary } from "@/lib/api/research";

/** How often a running research run is re-checked. */
export const RESEARCH_POLL_MS = 5000;

export interface ResearchWatch {
  /** The run that finished while this chat was watching it, until dismissed. */
  done: ResearchRunSummary | null;
  /** Look at the trip's latest run and, if it is running, follow it to the end. */
  check: () => void;
  dismiss: () => void;
}

/**
 * Follows the trip's deep-research run from the chat so the traveller learns it
 * finished without opening the Research tab. Only a run seen `running` here can
 * raise `done` — an old completed run never does. Any read failure (free tier
 * 403, no run 404, network) stops watching silently.
 */
export function useResearchWatch(
  tripId: string | undefined,
  enabled: boolean,
): ResearchWatch {
  const [done, setDone] = useState<{
    tripId: string;
    run: ResearchRunSummary;
  } | null>(null);
  // Bumped by `check` to start a fresh follow; the effect below owns the loop.
  const [checks, setChecks] = useState(0);
  // A read in flight or a poll scheduled: `check` must not start a second chain.
  const following = useRef(false);

  // Also runs on mount, so a run already going (page reload mid-run) is followed.
  useEffect(() => {
    if (!enabled || !tripId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let watchedRunId: string | null = null;

    const poll = async () => {
      following.current = true;
      let run: ResearchRunSummary;
      try {
        run = await getLatestResearch(tripId);
      } catch {
        if (!cancelled) following.current = false;
        return;
      }
      if (cancelled) return;
      if (run.status === "running") {
        watchedRunId = run.run_id;
        timer = setTimeout(() => void poll(), RESEARCH_POLL_MS);
        return;
      }
      following.current = false;
      if (run.status === "completed" && watchedRunId === run.run_id) {
        setDone({ tripId, run });
      }
    };

    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      following.current = false;
    };
  }, [enabled, tripId, checks]);

  const check = useCallback(() => {
    if (!following.current) setChecks((n) => n + 1);
  }, []);

  const dismiss = useCallback(() => setDone(null), []);

  return {
    done: done !== null && done.tripId === tripId ? done.run : null,
    check,
    dismiss,
  };
}
