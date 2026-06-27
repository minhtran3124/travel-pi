"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { streamBaseUrl } from "@/lib/api/client";
import { useUserId } from "@/lib/identity/useUserId";
import { fetchConversationMessages, type ChatRequest } from "@/lib/query/agent";
import { parseSSE } from "@/lib/stream/parseSSE";

const CONVERSATION_STORAGE_KEY = "travel.conversationId";

function readStoredConversationId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(CONVERSATION_STORAGE_KEY);
}

function writeStoredConversationId(id: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CONVERSATION_STORAGE_KEY, id);
}

function clearStoredConversationId(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(CONVERSATION_STORAGE_KEY);
}

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
  /** Called once an assistant turn finishes (stream end). */
  onTurnComplete?: () => void;
}

export interface UseAgentStream {
  messages: ChatMessage[];
  send: (text: string) => void;
  isStreaming: boolean;
  /** Set when the streaming turn fails (no /chat fallback). */
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
  /**
   * Clears the current conversation and starts fresh: resets conversationId,
   * clears persisted storage, and empties the message list.
   */
  newConversation: () => void;
}

function newId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Drives a single agent conversation: streams `/agent/stream` direct-to-origin
 * (bypassing the buffering Next proxy). Only the assistant's final answer is
 * rendered — sub-agent/tool activity events on the wire are ignored. Conversation
 * id is persisted across turns for continuity.
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
  // Prevents double-hydration when userId effect re-runs (e.g. strict-mode double-invoke).
  const hydratedRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  // Tracks the assistant message id for the current turn so resume() can
  // append continuation tokens into the same bubble.
  const assistantIdRef = useRef<string | null>(null);
  // Synchronous in-flight guard. `isStreaming` is React state (updated async),
  // so two send()/resume() calls in the same tick both read it as false and
  // both fire a request — producing duplicate turns. This ref flips
  // synchronously, blocking the second call immediately.
  const inFlightRef = useRef(false);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // On mount (once userId is ready): read persisted conversationId from storage,
  // then fetch + hydrate prior messages. Fails silently so new chats are never blocked.
  useEffect(() => {
    if (!userId || hydratedRef.current) return;

    const storedId = readStoredConversationId();
    if (!storedId) return;

    hydratedRef.current = true;
    conversationIdRef.current = storedId;

    fetchConversationMessages(storedId)
      .then((msgs) => {
        if (msgs.length > 0) {
          setMessages(
            msgs.map((m) => ({
              id: m.id,
              role: m.role,
              content: m.content,
            })),
          );
        }
      })
      .catch(() => {
        // Fail silently — start empty and let the user send a new message.
      });
  }, [userId]);

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
      if (
        message.length === 0 ||
        inFlightRef.current ||
        isStreaming ||
        interrupt !== null
      )
        return;
      if (!userId) {
        setError(t("errorIdentityNotReady"));
        return;
      }
      inFlightRef.current = true;

      // The BE mints a fresh thread whenever conversation_id is null (and echoes
      // the id back in the `start`/`done` events). To keep multi-turn memory we
      // pin a client-generated id on the first turn and reuse it for every
      // subsequent turn (the BE accepts a client-supplied id and keys the thread
      // on it).
      if (conversationIdRef.current === null) {
        const minted = newId();
        conversationIdRef.current = minted;
        writeStoredConversationId(minted);
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
            switch (event.type) {
              case "start":
                // Pin the server's conversation id for turn continuity.
                conversationIdRef.current = event.conversationId;
                writeStoredConversationId(event.conversationId);
                break;
              case "token":
                received = true;
                appendToAssistant(assistantId, event.text);
                break;
              case "reset":
                // Agent revised its answer (reflection re-ran the sub-agent) —
                // drop the superseded draft so only the final answer renders.
                setAssistant(assistantId, "");
                break;
              case "interrupt":
                received = true;
                sawInterrupt = true;
                // Prefer the conversationId echoed in the interrupt event.
                conversationIdRef.current = event.conversationId;
                writeStoredConversationId(event.conversationId);
                setInterrupt({
                  conversationId: event.conversationId,
                  payload: event.payload,
                });
                break;
              case "error":
                // In-band backend failure — route through the catch below.
                throw new Error(`agent error: ${event.code}`);
              // subagent / tool_call / tool_result / done: not surfaced — we only
              // render the assistant's final answer.
              default:
                break;
            }
          }

          if (!received) {
            throw new Error("stream produced no tokens");
          }
        } catch {
          if (controller.signal.aborted) return;

          // No /agent/chat fallback: surface the streaming failure directly so it
          // is visible instead of being masked by a silent non-streaming retry.
          // Keep any partial tokens already rendered.
          setError(
            received ? t("errorConnectionDropped") : t("errorUnavailable"),
          );
        } finally {
          inFlightRef.current = false;
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
      if (!userId || !pendingInterrupt || !assistantId || inFlightRef.current)
        return;
      inFlightRef.current = true;

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
            switch (event.type) {
              case "token":
                appendToAssistant(assistantId, event.text);
                break;
              case "reset":
                setAssistant(assistantId, "");
                break;
              case "error":
                throw new Error(`agent error: ${event.code}`);
              // Nested interrupts are not expected; start/done/subagent/tool
              // events are no-ops here.
              default:
                break;
            }
          }
        } catch {
          if (controller.signal.aborted) return;
          setError(t("errorResumeFailed"));
        } finally {
          inFlightRef.current = false;
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

  const newConversation = useCallback(() => {
    clearStoredConversationId();
    conversationIdRef.current = null;
    hydratedRef.current = false;
    setMessages([]);
    setError(null);
    setInterrupt(null);
  }, []);

  return { messages, send, isStreaming, error, interrupt, resume, newConversation };
}
