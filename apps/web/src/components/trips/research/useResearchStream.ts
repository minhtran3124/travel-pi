"use client";

import { useEffect, useRef, useState } from "react";

import { streamBaseUrl } from "@/lib/api/client";
import {
  readResearchStream,
  type ResearchEvent,
  type ResearchTodo,
} from "@/lib/stream/research";
import { authHeader } from "@/lib/supabase/authHeader";

// Lifecycle mirrors `components/chat/useAgentStream.ts`: a single direct-to-origin
// fetch against `streamBaseUrl()` (the buffering `/api/be` proxy would stall the
// stream), the Supabase JWT attached via `authHeader()`, and an AbortController
// held in a ref that is aborted on unmount and whenever `runId` changes. The
// research stream is read-only (no send/resume), so this hook only reduces the
// projected `ResearchEvent`s into render state.

export type ResearchStatus = "idle" | "streaming" | "done" | "error";

/** A subagent or tool tracked by name, carrying its latest reported status. */
export interface NamedStatus {
  name: string;
  status: string;
}

export interface ResearchFile {
  path: string;
  bytes: number;
}

export interface ResearchEvalState {
  iteration: number;
  result: string;
  explanation: string;
}

export interface ResearchTerminalError {
  code: string;
  message: string;
}

export interface ResearchStreamState {
  runId: string | null;
  tripId: string | null;
  /** Current plan checklist, replaced whole on each `research_phase`. */
  todos: ResearchTodo[];
  /** Latest status per subagent, upserted by name. */
  subagents: NamedStatus[];
  /** Latest status per tool, upserted by name. */
  tools: NamedStatus[];
  /** Dossier files seen so far, upserted by path (latest byte size). */
  files: ResearchFile[];
  /** Most recent rubric verdict, or `null` before any eval. */
  lastEval: ResearchEvalState | null;
  status: ResearchStatus;
  proposalReady: boolean;
  /** Set only on a terminal `research_error`. */
  error: ResearchTerminalError | null;
}

const INITIAL: ResearchStreamState = {
  runId: null,
  tripId: null,
  todos: [],
  subagents: [],
  tools: [],
  files: [],
  lastEval: null,
  status: "idle",
  proposalReady: false,
  error: null,
};

function upsertNamed(
  list: NamedStatus[],
  name: string,
  status: string,
): NamedStatus[] {
  const at = list.findIndex((e) => e.name === name);
  if (at === -1) return [...list, { name, status }];
  return list.map((e, i) => (i === at ? { name, status } : e));
}

function upsertFile(
  list: ResearchFile[],
  path: string,
  bytes: number,
): ResearchFile[] {
  const at = list.findIndex((f) => f.path === path);
  if (at === -1) return [...list, { path, bytes }];
  return list.map((f, i) => (i === at ? { path, bytes } : f));
}

/** Fold any terminal filename not already streamed as a `research_file` in. */
function mergeFileNames(list: ResearchFile[], paths: string[]): ResearchFile[] {
  let next = list;
  for (const path of paths) {
    if (!next.some((f) => f.path === path)) next = [...next, { path, bytes: 0 }];
  }
  return next;
}

/** Pure reducer folding one projected event into the render state. */
export function reduceResearchEvent(
  state: ResearchStreamState,
  event: ResearchEvent,
): ResearchStreamState {
  switch (event.type) {
    case "research_start":
      return { ...state, runId: event.runId, tripId: event.tripId, status: "streaming" };
    case "research_phase":
      return { ...state, todos: event.todos };
    case "research_subagent":
      return { ...state, subagents: upsertNamed(state.subagents, event.name, event.status) };
    case "research_tool":
      return { ...state, tools: upsertNamed(state.tools, event.name, event.status) };
    case "research_file":
      return { ...state, files: upsertFile(state.files, event.path, event.bytes) };
    case "research_eval":
      return {
        ...state,
        lastEval: {
          iteration: event.iteration,
          result: event.result,
          explanation: event.explanation,
        },
      };
    case "research_done":
      return {
        ...state,
        status: "done",
        proposalReady: event.proposalReady,
        files: mergeFileNames(state.files, event.files),
      };
    case "research_error":
      return {
        ...state,
        status: "error",
        error: { code: event.code, message: event.message },
      };
    default:
      return state;
  }
}

/**
 * Subscribes to `GET /agent/research/{run_id}/stream` and reduces the projected
 * progress events into render state. Passing `runId === null` holds the hook
 * idle (empty state). Changing `runId` or unmounting aborts the in-flight
 * stream and resets state for the new run.
 */
export function useResearchStream(runId: string | null): ResearchStreamState {
  const [state, setState] = useState<ResearchStreamState>(INITIAL);
  const [renderedFor, setRenderedFor] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Reset render state the moment `runId` changes — done during render (React's
  // recommended pattern for adjusting state on a prop change) rather than in the
  // effect, so a stale run's todos/files never flash before the new stream opens
  // and `research_start` re-confirms the ids.
  if (renderedFor !== runId) {
    setRenderedFor(runId);
    setState(runId ? { ...INITIAL, runId, status: "streaming" } : INITIAL);
  }

  useEffect(() => {
    if (!runId) return;

    const controller = new AbortController();
    abortRef.current = controller;

    void (async () => {
      try {
        const res = await fetch(
          `${streamBaseUrl()}/agent/research/${encodeURIComponent(runId)}/stream`,
          { headers: { ...(await authHeader()) }, signal: controller.signal },
        );
        if (!res.ok || !res.body) {
          throw new Error(`research stream failed: ${res.status}`);
        }
        let sawTerminal = false;
        for await (const event of readResearchStream(res)) {
          if (event.type === "research_done" || event.type === "research_error") {
            sawTerminal = true;
          }
          setState((prev) => reduceResearchEvent(prev, event));
        }
        // A clean EOF with no terminal event is still a failed run — surface it
        // rather than leaving the tab stuck in "streaming".
        if (!sawTerminal && !controller.signal.aborted) {
          setState((prev) =>
            prev.status === "done" || prev.status === "error"
              ? prev
              : {
                  ...prev,
                  status: "error",
                  error: { code: "stream", message: "stream ended early" },
                },
          );
        }
      } catch {
        // The unmount/runId-change cleanup aborts this controller; that is not a
        // failure, so leave state untouched. Any other drop before a terminal
        // event is surfaced as an error (a terminal event already set its own).
        if (controller.signal.aborted) return;
        setState((prev) =>
          prev.status === "done" || prev.status === "error"
            ? prev
            : {
                ...prev,
                status: "error",
                error: { code: "stream", message: "connection dropped" },
              },
        );
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    })();

    return () => controller.abort();
  }, [runId]);

  return state;
}
