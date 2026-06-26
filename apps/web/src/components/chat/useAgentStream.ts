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
  /** True after a turn degraded to (or failed at) the non-streaming fallback. */
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

          let received = false;
          for await (const chunk of parseSSE(res.body)) {
            received = true;
            appendToAssistant(assistantId, chunk);
          }
          if (!received) {
            throw new Error("stream produced no tokens");
          }
        } catch (streamErr) {
          if (controller.signal.aborted) return;
          // Fall back to the non-streaming sibling endpoint.
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
            void streamErr; // streaming error is superseded by the fallback failure
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
