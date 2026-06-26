"use client";

import { useQuery } from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
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
    queryFn: () => unwrap(client.GET("/agent/manifest")),
  });
}

/**
 * POST /agent/chat — the non-streaming sibling of `/agent/stream`. Used by the
 * widget as the SSE-error fallback: returns the full reply in one JSON body.
 */
export function chatFallback(body: ChatRequest): Promise<ChatResponse> {
  return unwrap(client.POST("/agent/chat", { body }));
}
