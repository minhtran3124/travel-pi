"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { streamBaseUrl } from "@/lib/api/client";
import { useUserId } from "@/lib/identity/useUserId";
import { fetchClaim, fetchConversationMessages, type ChatRequest } from "@/lib/query/agent";
import { authHeader } from "@/lib/supabase/authHeader";
import { createClient } from "@/lib/supabase/client";
import { parseSSE } from "@/lib/stream/parseSSE";

const CONVERSATION_STORAGE_KEY = "travel.conversationId";
const MODE_STORAGE_KEY = "travel.mode";
const CLAIMED_STORAGE_KEY = "travel.claimed";

type ChatMode = "fast" | "balanced" | "deep";

function readStoredMode(): ChatMode {
  if (typeof window === "undefined") return "balanced";
  const v = localStorage.getItem(MODE_STORAGE_KEY);
  if (v === "fast" || v === "balanced" || v === "deep") return v;
  return "balanced";
}

function writeStoredMode(mode: ChatMode): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(MODE_STORAGE_KEY, mode);
}

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

export type { ChatMode };

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
  /** Current response mode selection; persisted to localStorage. */
  mode: ChatMode;
  /** Change the response mode; persisted immediately. */
  setMode: (mode: ChatMode) => void;
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
   * True when the last message is an unanswered user turn (e.g. the page was
   * reloaded mid-stream, so the assistant reply was never persisted). The UI
   * surfaces a "retry" affordance in this state.
   */
  canRetry: boolean;
  /**
   * Re-answers the dangling last user turn. Re-sends that message with
   * `retry:true` (so the backend does not save a duplicate question) and streams
   * the reply into a fresh assistant bubble.
   */
  retry: () => void;
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
  const [mode, setModeState] = useState<ChatMode>(readStoredMode);

  const setMode = useCallback((m: ChatMode) => {
    writeStoredMode(m);
    setModeState(m);
  }, []);

  const conversationIdRef = useRef<string | null>(null);
  // Prevents double-hydration when userId effect re-runs (e.g. strict-mode double-invoke).
  const hydratedRef = useRef(false);
  // Prevents claim from running twice (strict-mode double-invoke guard).
  const claimedRef = useRef(false);
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

  // On mount (once userId is ready): optionally claim anonymous history into the
  // logged-in account (once per account/browser), then hydrate prior messages.
  // Claim completes before hydration so newly-claimed conversations are visible.
  // Both steps fail silently so new chats are never blocked.
  useEffect(() => {
    if (!userId || claimedRef.current) return;
    claimedRef.current = true; // strict-mode double-invoke guard

    void (async () => {
      // --- Claim step (logged-in users only, once per account/browser) ---
      if (!localStorage.getItem(CLAIMED_STORAGE_KEY)) {
        const { data } = await createClient().auth.getSession();
        const session = data.session;
        if (session) {
          try {
            await fetchClaim(userId);
            localStorage.setItem(CLAIMED_STORAGE_KEY, session.user.id);
          } catch {
            // Fail silently — 403 (source is a registered account) or network error
          }
        }
      }

      // --- Hydrate step ---
      if (hydratedRef.current) return;
      hydratedRef.current = true;

      const storedId = readStoredConversationId();
      if (!storedId) return;
      conversationIdRef.current = storedId;

      fetchConversationMessages(storedId, userId)
        .then((msgs) => {
          if (msgs.length > 0) {
            setMessages(
              msgs.map((m) => ({ id: m.id, role: m.role, content: m.content })),
            );
          }
        })
        .catch(() => {
          // Fail silently — start empty and let the user send a new message.
        });
    })();
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
        retry: false,
        mode,
      };

      const controller = new AbortController();
      abortRef.current = controller;

      void (async () => {
        let received = false;
        let sawInterrupt = false;
        try {
          const res = await fetch(`${streamBaseUrl()}/agent/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...(await authHeader()) },
            body: JSON.stringify(body),
            signal: controller.signal,
          });

          if (res.status === 429) {
            throw new Error("quota");
          }
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
        } catch (err) {
          if (controller.signal.aborted) return;

          // No /agent/chat fallback: surface the streaming failure directly so it
          // is visible instead of being masked by a silent non-streaming retry.
          // Keep any partial tokens already rendered.
          if (err instanceof Error && err.message === "quota") {
            setError(t("errorQuota"));
          } else {
            setError(
              received ? t("errorConnectionDropped") : t("errorUnavailable"),
            );
          }
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
    [appendToAssistant, interrupt, isStreaming, mode, onTurnComplete, setAssistant, t, userId],
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
        retry: false,
        mode,
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
            headers: { "Content-Type": "application/json", ...(await authHeader()) },
            body: JSON.stringify(body),
            signal: controller.signal,
          });

          if (res.status === 429) {
            throw new Error("quota");
          }
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
        } catch (err) {
          if (controller.signal.aborted) return;
          if (err instanceof Error && err.message === "quota") {
            setError(t("errorQuota"));
          } else {
            setError(t("errorResumeFailed"));
          }
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
    [appendToAssistant, interrupt, mode, onTurnComplete, setAssistant, t, userId],
  );

  const retry = useCallback(() => {
    if (inFlightRef.current || isStreaming || interrupt !== null) return;
    if (!userId) {
      setError(t("errorIdentityNotReady"));
      return;
    }
    const last = messages[messages.length - 1];
    const conversationId = conversationIdRef.current;
    // Only meaningful for a dangling user turn on an existing conversation.
    if (!last || last.role !== "user" || !conversationId) return;
    inFlightRef.current = true;

    const assistantId = newId();
    assistantIdRef.current = assistantId;
    setError(null);
    // No new user bubble — the question is already on screen and in the DB.
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "" },
    ]);
    setIsStreaming(true);

    const body: ChatRequest = {
      message: last.content,
      user_id: userId,
      trip_id: tripIdRef.current ?? null,
      conversation_id: conversationId,
      // Re-answer the existing user turn without re-saving the question.
      retry: true,
      mode,
    };

    const controller = new AbortController();
    abortRef.current = controller;

    void (async () => {
      let received = false;
      let sawInterrupt = false;
      try {
        const res = await fetch(`${streamBaseUrl()}/agent/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(await authHeader()) },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        if (res.status === 429) {
          throw new Error("quota");
        }
        if (!res.ok || !res.body) {
          throw new Error(`retry failed: ${res.status}`);
        }

        for await (const event of parseSSE(res.body)) {
          switch (event.type) {
            case "start":
              conversationIdRef.current = event.conversationId;
              writeStoredConversationId(event.conversationId);
              break;
            case "token":
              received = true;
              appendToAssistant(assistantId, event.text);
              break;
            case "reset":
              setAssistant(assistantId, "");
              break;
            case "interrupt":
              received = true;
              sawInterrupt = true;
              conversationIdRef.current = event.conversationId;
              writeStoredConversationId(event.conversationId);
              setInterrupt({
                conversationId: event.conversationId,
                payload: event.payload,
              });
              break;
            case "error":
              throw new Error(`agent error: ${event.code}`);
            default:
              break;
          }
        }

        if (!received) {
          throw new Error("stream produced no tokens");
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof Error && err.message === "quota") {
          setError(t("errorQuota"));
        } else {
          setError(received ? t("errorConnectionDropped") : t("errorUnavailable"));
        }
      } finally {
        inFlightRef.current = false;
        if (!controller.signal.aborted) {
          setIsStreaming(false);
          if (!sawInterrupt) {
            onTurnComplete?.();
          }
        }
        if (abortRef.current === controller) abortRef.current = null;
      }
    })();
  }, [
    appendToAssistant,
    interrupt,
    isStreaming,
    messages,
    mode,
    onTurnComplete,
    setAssistant,
    t,
    userId,
  ]);

  const newConversation = useCallback(() => {
    clearStoredConversationId();
    conversationIdRef.current = null;
    hydratedRef.current = false;
    setMessages([]);
    setError(null);
    setInterrupt(null);
  }, []);

  const lastMessage = messages[messages.length - 1];
  const canRetry =
    !isStreaming && interrupt === null && lastMessage?.role === "user";

  return {
    messages,
    send,
    isStreaming,
    error,
    mode,
    setMode,
    interrupt,
    resume,
    canRetry,
    retry,
    newConversation,
  };
}
