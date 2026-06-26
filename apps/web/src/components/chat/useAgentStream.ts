"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { streamBaseUrl } from "@/lib/api/client";
import { useUserId } from "@/lib/identity/useUserId";
import { chatFallback, type ChatRequest } from "@/lib/query/agent";
import { parseSSE } from "@/lib/stream/parseSSE";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  /** Grows token-by-token while an assistant turn streams. */
  content: string;
}

export interface UseAgentStreamOptions {
  tripId?: string;
  /** Called once an assistant turn finishes (stream end or fallback reply). */
  onTurnComplete?: () => void;
}

export interface UseAgentStream {
  messages: ChatMessage[];
  send: (text: string) => void;
  isStreaming: boolean;
  /**
   * Set only when a turn fails outright — i.e. BOTH the stream and the
   * non-streaming fallback failed. A silent stream→fallback recovery leaves
   * this null.
   */
  error: string | null;
}

function newId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Drives a single agent conversation: streams `/agent/stream` direct-to-origin
 * (bypassing the buffering Next proxy) and falls back to the non-streaming
 * `POST /agent/chat` on any fetch/stream error. Conversation id is persisted
 * across turns for continuity.
 */
export function useAgentStream(
  options: UseAgentStreamOptions = {},
): UseAgentStream {
  const { onTurnComplete } = options;
  const tripIdRef = useRef(options.tripId);
  useEffect(() => {
    tripIdRef.current = options.tripId;
  }, [options.tripId]);

  const userId = useUserId();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const conversationIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const appendToAssistant = useCallback((id: string, chunk: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content: m.content + chunk } : m)),
    );
  }, []);

  const setAssistant = useCallback((id: string, content: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content } : m)),
    );
  }, []);

  const send = useCallback(
    (text: string) => {
      const message = text.trim();
      if (message.length === 0 || isStreaming) return;
      if (!userId) {
        setError("Identity not ready yet. Please try again in a moment.");
        return;
      }

      // The streaming endpoint returns plain text (no conversation_id), and the
      // BE mints a fresh thread whenever conversation_id is null. To keep
      // multi-turn memory we pin a client-generated id on the first turn and
      // reuse it for every subsequent turn (the BE accepts a client-supplied id
      // and keys the thread on it).
      if (conversationIdRef.current === null) {
        conversationIdRef.current = newId();
      }

      const assistantId = newId();
      setError(null);
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "user", content: message },
        { id: assistantId, role: "assistant", content: "" },
      ]);
      setIsStreaming(true);

      const body: ChatRequest = {
        message,
        user_id: userId,
        trip_id: tripIdRef.current ?? null,
        conversation_id: conversationIdRef.current,
      };

      const controller = new AbortController();
      abortRef.current = controller;

      void (async () => {
        let received = false;
        try {
          const res = await fetch(`${streamBaseUrl()}/agent/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
            signal: controller.signal,
          });

          if (!res.ok || !res.body) {
            throw new Error(`stream failed: ${res.status}`);
          }

          for await (const chunk of parseSSE(res.body)) {
            received = true;
            appendToAssistant(assistantId, chunk);
          }
          if (!received) {
            throw new Error("stream produced no tokens");
          }
        } catch {
          if (controller.signal.aborted) return;

          // If the stream already produced tokens the agent may have performed
          // server-side writes; re-invoking the non-idempotent chat fallback on
          // the same thread would risk duplicate mutations. Only fall back when
          // NOTHING was received — otherwise keep the partial text and surface
          // the interruption.
          if (received) {
            setError(
              "The connection dropped mid-reply. The response above may be incomplete.",
            );
          } else {
            try {
              const reply = await chatFallback(body);
              conversationIdRef.current = reply.conversation_id;
              setAssistant(assistantId, reply.reply);
            } catch {
              setError(
                "The travel assistant is unavailable right now. Please try again later.",
              );
              setAssistant(
                assistantId,
                "Sorry — I could not reach the travel assistant.",
              );
            }
          }
        } finally {
          if (!controller.signal.aborted) {
            setIsStreaming(false);
            onTurnComplete?.();
          }
          if (abortRef.current === controller) abortRef.current = null;
        }
      })();
    },
    [appendToAssistant, isStreaming, onTurnComplete, setAssistant, userId],
  );

  return { messages, send, isStreaming, error };
}
