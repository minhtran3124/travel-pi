"use client";

// Typed client for the deep-research **agent surface** (design §5). Every route
// lives under `/agent/...`, so it authenticates on the Supabase JWT — never the
// REST `X-User-Id` identity. Non-streaming calls go through the buffering
// `/api/be` Next proxy (same as the other agent-surface fetchers in
// `lib/query/agent.ts`); the live progress SSE goes direct-to-origin and lives
// in `components/trips/research/useResearchStream.ts` instead.
//
// Hand-typed on purpose: the BE research router lands in a later wave and
// `pnpm gen:api` (which needs a running API with the flag on) is owned by Task
// 7.1. Types here mirror design §5 and are provisional until the generated
// `schema` is regenerated against the real routes.

import { authHeader } from "@/lib/supabase/authHeader";

// Agent-surface calls ride the same `/api/be` proxy as the chat history
// fetchers; only the SSE stream bypasses it (see the stream hook).
const AGENT_BASE = "/api/be";

// ── Wire types (design §5) ────────────────────────────────────────────────────

export interface StartResearchBody {
  instruction?: string;
  language?: string;
}

/** 202 payload from a start/revise POST. */
export interface StartResearchResponse {
  run_id: string;
  thread_turn: number;
}

/**
 * Latest-run summary for a trip (`GET /agent/trips/{trip_id}/research`), and the
 * same projected state returned by `GET /agent/research/{run_id}`. Mirrors the
 * backend `ResearchStatusResponse` (see `apps/web/src/lib/api/schema.d.ts`)
 * field-for-field: `trip_id` is nullable and the turn is `thread_turn`.
 */
export interface ResearchRunSummary {
  run_id: string;
  trip_id: string | null;
  status: string;
  thread_turn: number;
  files: string[];
  proposal_ready: boolean;
  /** The grader's verdict; `needs_review` = it never accepted the dossier. */
  review?: "passed" | "needs_review" | null;
}

/** File content envelope (`GET`/`PUT /agent/research/{run_id}/files/{path}`). */
export interface ResearchFileContent {
  content: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function agentGet<T>(path: string): Promise<T> {
  const res = await fetch(`${AGENT_BASE}${path}`, {
    headers: { ...(await authHeader()) },
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

async function agentSend<T>(
  method: "POST" | "PUT",
  path: string,
  body: unknown,
): Promise<T> {
  const res = await fetch(`${AGENT_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

function filePath(runId: string, path: string): string {
  // The BE route is `/files/{path:path}`, so the segment may contain slashes;
  // encode each part, keeping the separators.
  const encoded = path
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/");
  return `/agent/research/${encodeURIComponent(runId)}/files/${encoded}`;
}

// ── Public API ─────────────────────────────────────────────────────────────────

/** Start a research run for a trip (turn 1). `POST /agent/trips/{id}/research`. */
export function startResearch(
  tripId: string,
  body: StartResearchBody = {},
): Promise<StartResearchResponse> {
  return agentSend(
    "POST",
    `/agent/trips/${encodeURIComponent(tripId)}/research`,
    body,
  );
}

/**
 * Revise an existing run with a follow-up instruction — the next turn on the
 * same checkpointed thread. `POST /agent/research/{run_id}/revise`; the BE
 * resolves the prior run's trip and enforces run ownership (`_owned_run`).
 */
export function reviseResearch(
  runId: string,
  instruction: string,
): Promise<StartResearchResponse> {
  return agentSend(
    "POST",
    `/agent/research/${encodeURIComponent(runId)}/revise`,
    { instruction },
  );
}

/** Latest run summary for a trip, or throws on 404. */
export function getLatestResearch(tripId: string): Promise<ResearchRunSummary> {
  return agentGet(`/agent/trips/${encodeURIComponent(tripId)}/research`);
}

/** Projected state (status + file index) for one run. */
export function getResearch(runId: string): Promise<ResearchRunSummary> {
  return agentGet(`/agent/research/${encodeURIComponent(runId)}`);
}

/**
 * The run's file index. Design §5 has no dedicated list route — the index is a
 * field of the status response — so this derives it from `getResearch` rather
 * than hitting a non-existent endpoint (see the report's Deviations note).
 */
export async function getResearchFiles(runId: string): Promise<string[]> {
  const detail = await getResearch(runId);
  return detail.files;
}

/** One file's markdown content. */
export async function getResearchFile(
  runId: string,
  path: string,
): Promise<string> {
  const res = await agentGet<ResearchFileContent>(filePath(runId, path));
  return res.content;
}

/** Persist a user edit to one file. */
export async function putResearchFile(
  runId: string,
  path: string,
  content: string,
): Promise<void> {
  await agentSend<ResearchFileContent>("PUT", filePath(runId, path), {
    content,
  });
}
