"use client";

import { useTranslations } from "next-intl";
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

/** Pending HITL interrupt from the agent — shown as an approve/reject prompt. */
export interface InterruptState {
  conversationId: string;
  payload: { type: string; draft: string };
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
  /**
   * Non-null when the agent emitted an `interrupt` event and is waiting for a
   * human decision (approve/reject) before continuing.
   */
  interrupt: InterruptState | null;
  /**
   * Resumes the agent after an interrupt. Sends `{resume:{approved}}` to
   * `/agent/stream` and streams the continuation into the same message bubble.
   */
  resume: (approved: boolean) => void;
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
 *
 * HITL: when the agent emits `event: interrupt`, the hook surfaces an
 * `interrupt` state and a `resume(approved)` action. The UI shows an
 * approve/reject prompt; on decision the hook streams the continuation tokens
 * into the same assistant message bubble and calls `onTurnComplete`.
 */
export function useAgentStream(
  options: UseAgentStreamOptions = {},
): UseAgentStream {
  const t = useTranslations("Chat");
  const { onTurnComplete } = options;
  const tripIdRef = useRef(options.tripId);
  useEffect(() => {
    tripIdRef.current = options.tripId;
  }, [options.tripId]);

  const userId = useUserId();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interrupt, setInterrupt] = useState<InterruptState | null>(null);

  const conversationIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Tracks the assistant message id for the current turn so resume() can
  // append continuation tokens into the same bubble.
  const assistantIdRef = useRef<string | null>(null);

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
      if (message.length === 0 || isStreaming || interrupt !== null) return;
      if (!userId) {
        setError(t("errorIdentityNotReady"));
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
      assistantIdRef.current = assistantId;
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
        let sawInterrupt = false;
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

          for await (const event of parseSSE(res.body)) {
            received = true;
            if (event.type === "token") {
              appendToAssistant(assistantId, event.text);
            } else if (event.type === "reset") {
              // Agent revised its answer (reflection re-ran the sub-agent) —
              // drop the superseded draft so only the final answer renders.
              setAssistant(assistantId, "");
            } else if (event.type === "interrupt") {
              sawInterrupt = true;
              // Prefer the conversationId echoed in the interrupt event.
              conversationIdRef.current = event.conversationId;
              setInterrupt({
                conversationId: event.conversationId,
                payload: event.payload,
              });
            }
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
            setError(t("errorConnectionDropped"));
          } else {
            try {
              const reply = await chatFallback(body);
              conversationIdRef.current = reply.conversation_id;
              setAssistant(assistantId, reply.reply);
            } catch {
              setError(t("errorUnavailable"));
              setAssistant(assistantId, t("fallbackCouldNotReach"));
            }
          }
        } finally {
          if (!controller.signal.aborted) {
            setIsStreaming(false);
            // Delay onTurnComplete until after the user resolves the interrupt.
            if (!sawInterrupt) {
              onTurnComplete?.();
            }
          }
          if (abortRef.current === controller) abortRef.current = null;
        }
      })();
    },
    [appendToAssistant, interrupt, isStreaming, onTurnComplete, setAssistant, t, userId],
  );

  const resume = useCallback(
    (approved: boolean) => {
      const assistantId = assistantIdRef.current;
      const pendingInterrupt = interrupt;
      if (!userId || !pendingInterrupt || !assistantId) return;

      const body: ChatRequest = {
        resume: { approved },
        user_id: userId,
        trip_id: tripIdRef.current ?? null,
        conversation_id: pendingInterrupt.conversationId,
      };

      setInterrupt(null);
      setIsStreaming(true);
      setError(null);

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
            throw new Error(`resume failed: ${res.status}`);
          }

          for await (const event of parseSSE(res.body)) {
            if (event.type === "token") {
              appendToAssistant(assistantId, event.text);
            } else if (event.type === "reset") {
              setAssistant(assistantId, "");
            }
            // Nested interrupts are not expected; ignore if they appear.
          }
        } catch {
          if (controller.signal.aborted) return;
          setError(t("errorResumeFailed"));
        } finally {
          if (!controller.signal.aborted) {
            setIsStreaming(false);
            onTurnComplete?.();
          }
          if (abortRef.current === controller) abortRef.current = null;
        }
      })();
    },
    [appendToAssistant, interrupt, onTurnComplete, setAssistant, t, userId],
  );

  return { messages, send, isStreaming, error, interrupt, resume };
}
