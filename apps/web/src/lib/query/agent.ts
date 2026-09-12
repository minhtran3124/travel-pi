"use client";

import { useQuery } from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";
import { authHeader } from "@/lib/supabase/authHeader";

export type AgentManifest = components["schemas"]["AgentManifest"];
export type ToolManifestEntry = components["schemas"]["ToolManifestEntry"];
export type ChatRequest = components["schemas"]["ChatRequest"];
export type ChatResponse = components["schemas"]["ChatResponse"];

// --- History types (mirror app/schemas/agent.py:67-83) -----------------------

export interface Conversation {
  id: string;
  user_id: string;
  trip_id: string | null;
  title: string | null;
  domain: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls: unknown | null;
  created_at: string;
  /** Effective feedback state for an assistant message; `null` for user
   * messages and for an unrated assistant message (schema.d.ts `Message`). */
  feedback?: components["schemas"]["EffectiveFeedback"] | null;
}

/** Full message list for a conversation, including any pending interrupt state.
 * Mirrors the BE ConversationMessages schema (app/schemas/agent.py). The
 * `interrupt_payload` shape matches `InterruptState.payload` in
 * `components/chat/useAgentStream.ts`. */
export interface ConversationMessages {
  messages: Message[];
  interrupt_pending: boolean;
  interrupt_payload: { type: string; draft: string } | null;
}

/** Thrown by `fetchClaim` on a non-ok response; carries the HTTP status. */
export class ClaimError extends Error {
  status: number;
  constructor(status: number, message?: string) {
    super(message ?? `fetchClaim: ${status}`);
    this.name = "ClaimError";
    this.status = status;
  }
}

// --- History fetchers --------------------------------------------------------

/** GET /agent/conversations?user_id=... */
export async function fetchConversations(
  userId: string,
): Promise<Conversation[]> {
  const res = await fetch(
    `/api/be/agent/conversations?user_id=${encodeURIComponent(userId)}`,
    { headers: await authHeader() },
  );
  if (!res.ok) throw new Error(`fetchConversations: ${res.status}`);
  return res.json() as Promise<Conversation[]>;
}

/** GET /agent/conversations/{conversationId}/messages */
export async function fetchConversationMessages(
  conversationId: string,
  userId: string,
): Promise<ConversationMessages> {
  // Pass the anonymous userId so the owner check passes when logged out; when a
  // bearer token is present the BE uses the JWT sub and ignores this param.
  const res = await fetch(
    `/api/be/agent/conversations/${encodeURIComponent(conversationId)}/messages?user_id=${encodeURIComponent(userId)}`,
    { headers: await authHeader() },
  );
  if (!res.ok) throw new Error(`fetchConversationMessages: ${res.status}`);
  return res.json() as Promise<ConversationMessages>;
}

/** POST /agent/conversations/claim — migrate anonymous conversations to the logged-in account */
export async function fetchClaim(
  anonymousUserId: string,
): Promise<{ claimed: number }> {
  const res = await fetch("/api/be/agent/conversations/claim", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify({ anonymous_user_id: anonymousUserId }),
  });
  if (!res.ok) throw new ClaimError(res.status);
  return res.json() as Promise<{ claimed: number }>;
}

/**
 * GET /agent/manifest — the agent's advertised subagents + tools. Source for
 * the widget's quick-reply chips. Degrades silently (the widget hides chips on
 * error), so retry is disabled to fail fast when the agent is unreachable.
 */
export function useManifest() {
  return useQuery({
    queryKey: qk.manifest(),
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: () => unwrap(client.GET("/agent/manifest")),
  });
}
