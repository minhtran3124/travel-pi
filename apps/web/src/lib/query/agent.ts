"use client";

import { useQuery } from "@tanstack/react-query";

import { client } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type AgentManifest = components["schemas"]["AgentManifest"];
export type ToolManifestEntry = components["schemas"]["ToolManifestEntry"];
export type ChatRequest = components["schemas"]["ChatRequest"];
export type ChatResponse = components["schemas"]["ChatResponse"];

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
    queryFn: async () => {
      const { data, error } = await client.GET("/agent/manifest");
      if (error) throw error;
      return data;
    },
  });
}

/**
 * POST /agent/chat — the non-streaming sibling of `/agent/stream`. Used by the
 * widget as the SSE-error fallback: returns the full reply in one JSON body.
 */
export async function chatFallback(body: ChatRequest): Promise<ChatResponse> {
  const { data, error } = await client.POST("/agent/chat", { body });
  if (error) throw error;
  return data;
}
