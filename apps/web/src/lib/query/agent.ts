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
): Promise<Message[]> {
  const res = await fetch(
    `/api/be/agent/conversations/${encodeURIComponent(conversationId)}/messages`,
    { headers: await authHeader() },
  );
  if (!res.ok) throw new Error(`fetchConversationMessages: ${res.status}`);
  return res.json() as Promise<Message[]>;
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
  if (!res.ok) throw new Error(`fetchClaim: ${res.status}`);
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
