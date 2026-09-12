"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { streamBaseUrl } from "@/lib/api/client";
import { useIdentity } from "@/lib/identity/useUserId";
import {
  ClaimError,
  fetchClaim,
  fetchConversationMessages,
  type ChatRequest,
} from "@/lib/query/agent";
import type { EffectiveFeedback } from "@/lib/query/feedback";
import { panelKey, type PanelArtifact } from "@/lib/stream/panel";
import { authHeader } from "@/lib/supabase/authHeader";
import { parseSSE, type SSEEvent } from "@/lib/stream/parseSSE";
import { createSmoothReveal, type SmoothReveal } from "./smoothReveal";

const CONVERSATION_STORAGE_KEY = "travel.conversationId";
// The pre-auth anonymous id (once minted by IdentityProvider). Its presence is
// the one-shot signal to claim legacy anonymous history on first sign-in.
const LEGACY_ANON_STORAGE_KEY = "travel.userId";

// --- Smooth reveal tuning ---------------------------------------------------
// Base typewriter speed for streaming assistant text (chars/second). Lower =
// slower, more deliberate reveal.
const REVEAL_CHARS_PER_SEC = 40;
// Upper bound on how far the on-screen reveal may lag behind the wire. When the
// backlog would take longer than this to drain at the base speed, the reveal
// speeds up so it never falls more than ~this many seconds behind. Kept generous
// so the readable base speed governs typical answers; only very long bursts
// (backlog > CHARS_PER_SEC * MAX_LAG_SEC chars) get sped up to bound the tail.
const REVEAL_MAX_LAG_SEC = 6;

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

/**
 * One tool invocation surfaced in an assistant turn's activity trail. `tool` is
 * the raw wire tool name (the UI resolves it to a localized label); `subagent`
 * is the active specialist when the call fired, or `null` if none was announced.
 */
export type ActivityStep = {
  id: string;
  tool: string;
  subagent: string | null;
  status: "running" | "ok" | "error";
};

export interface ChatMessage {
  id: string;
  role: ChatRole;
  /** Grows token-by-token while an assistant turn streams. */
  content: string;
  /** Tool/subagent steps produced during this turn (assistant turns only). */
  activity: ActivityStep[];
  /** Structured panel artifacts produced during this turn, in arrival order. */
  panels: PanelArtifact[];
  /** Wall-clock duration of the turn in ms; set once the turn ends. */
  elapsedMs?: number;
  /**
   * Persisted id of this assistant message — the handle feedback is filed
   * against. Assigned ONLY from server history or a successful SSE `done`
   * (DESIGN §7.1); absent on streaming, interrupted, stopped and failed turns,
   * so its presence is the "complete + rateable" signal for the UI.
   */
  serverMessageId?: string;
  /** Effective feedback state reloaded from history; `null` when unrated. */
  feedback?: EffectiveFeedback | null;
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
   * Aborts the in-flight streaming turn on the user's request. Marks the abort
   * as deliberate so the finally-block still resets `isStreaming`/`elapsedMs`
   * (and fires `onTurnComplete` unless an interrupt was seen), unlike the
   * unmount-cleanup abort which leaves state untouched.
   */
  stop: () => void;
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
   * Regenerates the last completed assistant turn: drops that answer from the
   * transcript and re-runs the question with `retry:true` (no duplicate user
   * bubble, no re-saved question row).
   */
  regenerate: () => void;
  /**
   * Clears the current conversation and starts fresh: resets conversationId,
   * clears persisted storage, and empties the message list.
   */
  newConversation: () => void;
  /**
   * Structured side-panel payloads emitted by tools this conversation, latest
   * per panel key: kind + places category (a new route query replaces the
   * prior route panel). The chat drawer renders these by key.
   */
  panels: PanelArtifact[];
  /**
   * Language the streamed panels were localized to (BCP-47 short code, e.g.
   * "vi"). Carried from the `panel`/`done` SSE events so the drawer can render
   * the panel subtree in the traveller's language. Defaults to "en" and only
   * changes when an event supplies a `language`.
   */
  panelLanguage: string;
  /**
   * Context-aware follow-up suggestion keys from the last completed turn; empty
   * until a turn finishes / while a new turn is in flight.
   */
  suggestions: string[];
}

/** Replace any existing panel of the same key — latest wins, newest last. */
function upsertPanelByKey(
  prev: PanelArtifact[],
  next: PanelArtifact,
): PanelArtifact[] {
  return [...prev.filter((p) => panelKey(p) !== panelKey(next)), next];
}

function newId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** Content for a message the user deliberately stopped mid-turn: a friendly
 * placeholder if nothing arrived yet, else a small note appended to whatever
 * streamed in before Stop was clicked. */
function withStoppedContent(content: string, t: (key: string) => string): string {
  return content.trim() ? `${content}\n\n${t("stoppedSuffix")}` : t("stoppedEmpty");
}

/**
 * Final shape of the assistant bubble once its turn ends. A deliberate Stop
 * rewrites the content (stopped suffix / placeholder), so even when it lands
 * after `done` already recorded a `serverMessageId`, the bubble no longer
 * matches the persisted row — drop the id so the turn is not rateable
 * (DESIGN §7.1: stopped turns never show feedback).
 */
function settleTurn(
  m: ChatMessage,
  wasStopped: boolean,
  startedAt: number,
  t: (key: string) => string,
): ChatMessage {
  const next: ChatMessage = {
    ...m,
    content: wasStopped ? withStoppedContent(m.content, t) : m.content,
    elapsedMs: Date.now() - startedAt,
  };
  if (wasStopped) delete next.serverMessageId;
  return next;
}

/**
 * Drives a single agent conversation: streams `/agent/stream` direct-to-origin
 * (bypassing the buffering Next proxy). The assistant's final answer streams into
 * the message bubble; sub-agent/tool activity and panel events are surfaced onto
 * that turn's `activity` / `panels`. Conversation id is persisted across turns.
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

  const { userId, status } = useIdentity();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interrupt, setInterrupt] = useState<InterruptState | null>(null);
  const [panels, setPanels] = useState<PanelArtifact[]>([]);
  const [panelLanguage, setPanelLanguage] = useState("en");
  const [suggestions, setSuggestions] = useState<string[]>([]);

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
  // Distinguishes a deliberate user Stop from the unmount-cleanup abort. Only a
  // user Stop should still run the finally-block's state reset; set true by
  // stop(), consumed and cleared inside each stream loop's finally.
  const userStoppedRef = useRef(false);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // Once signed in: one-shot claim of any legacy anonymous history into the
  // account, then hydrate prior messages. Neither runs while signed out or
  // loading (no anonymous streaming survives the auth gate). Claim completes
  // before hydration so newly-claimed conversations are visible. Both steps fail
  // silently so new chats are never blocked.
  useEffect(() => {
    if (status !== "signed-in" || !userId || claimedRef.current) return;
    claimedRef.current = true; // strict-mode double-invoke guard

    void (async () => {
      // --- Legacy claim step (one-shot: the old anon id, if any) ---
      const anonId = localStorage.getItem(LEGACY_ANON_STORAGE_KEY);
      if (anonId) {
        try {
          await fetchClaim(anonId);
          // Success: the anon history is now migrated — drop the one-shot key.
          localStorage.removeItem(LEGACY_ANON_STORAGE_KEY);
        } catch (err) {
          // 403 = the anon id belongs to a registered account; nothing to claim,
          // so drop the key. Any other failure (incl. a network TypeError, which
          // is never a ClaimError) keeps the key so the next open retries — and
          // surfaces a soft error. Never `return` here: hydration below must
          // still run in this same IIFE regardless of the claim outcome.
          if (err instanceof ClaimError && err.status === 403) {
            localStorage.removeItem(LEGACY_ANON_STORAGE_KEY);
          } else {
            setError(t("errorClaimFailed"));
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
        .then(({ messages, interrupt_pending, interrupt_payload }) => {
          const mapped: ChatMessage[] = messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            activity: [],
            panels: [],
            ...(m.role === "assistant"
              ? { serverMessageId: m.id, feedback: m.feedback ?? null }
              : {}),
          }));

          if (interrupt_pending) {
            // Rehydrate the pending HITL prompt so resume() has a target bubble.
            const last = messages[messages.length - 1];
            if (last && last.role === "assistant") {
              assistantIdRef.current = last.id;
              // The interrupted turn is not complete — never rateable.
              delete mapped[mapped.length - 1].serverMessageId;
            } else {
              // No trailing assistant turn (interrupt fired before any tokens):
              // add a fresh empty bubble for the resumed continuation.
              const freshId = newId();
              mapped.push({
                id: freshId,
                role: "assistant",
                content: "",
                activity: [],
                panels: [],
              });
              assistantIdRef.current = freshId;
            }
            setMessages(mapped);
            setInterrupt({
              conversationId: storedId,
              payload: interrupt_payload!,
            });
          } else if (mapped.length > 0) {
            setMessages(mapped);
          }
        })
        .catch(() => {
          // Fail silently — start empty and let the user send a new message.
        });
    })();
  }, [status, userId]);

  // Carry the panel language from `panel`/`done` events. Called from every panel
  // and done handler across the send/resume/retry flows so the three stay in
  // sync. Missing `language` leaves the current value (default "en") untouched.
  const applyPanelLanguage = useCallback((language?: string) => {
    if (language) setPanelLanguage(language);
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

  // Record the persisted message id carried by a successful `done` so the
  // feedback controls can render (DESIGN §7.1). `done` after an interrupt
  // carries `null` — nothing to record, the turn stays unrateable.
  const markPersisted = useCallback((id: string, serverMessageId: string | null) => {
    if (!serverMessageId) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, serverMessageId } : m)),
    );
  }, []);

  // Append a structured panel to the streaming assistant message's own `panels`
  // (per-turn), alongside the flat `panels` state the drawer consumes.
  const attachPanelToMessage = useCallback(
    (id: string, panel: PanelArtifact) => {
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== id) return m;
          // The graph can re-emit a panel for the same result (reflection /
          // revision passes re-run the tool under a fresh call id) — upsert by
          // key, mirroring the drawer's upsert-by-key: one card per panel key,
          // always carrying the latest payload.
          const at = m.panels.findIndex(
            (existing) => panelKey(existing) === panelKey(panel),
          );
          const panels =
            at === -1
              ? [...m.panels, panel]
              : m.panels.map((existing, i) => (i === at ? panel : existing));
          return { ...m, panels };
        }),
      );
    },
    [],
  );

  // Surface subagent/tool_call/tool_result events onto the streaming assistant
  // message's activity trail. `specialist` is a per-turn holder tracking the
  // active sub-agent so tool steps can attribute themselves. Returns true when
  // the event was an activity event (handled here), false otherwise. Shared by
  // the send / resume / retry loops so all three stay consistent.
  const handleActivityEvent = useCallback(
    (
      id: string,
      event: SSEEvent,
      specialist: { current: string | null },
    ): boolean => {
      switch (event.type) {
        case "subagent":
          specialist.current = event.name || null;
          return true;
        case "tool_call": {
          const step: ActivityStep = {
            id: event.id,
            tool: event.name,
            subagent: specialist.current ?? event.subagent,
            status: "running",
          };
          setMessages((prev) =>
            prev.map((m) =>
              m.id === id ? { ...m, activity: [...m.activity, step] } : m,
            ),
          );
          return true;
        }
        case "tool_result":
          setMessages((prev) =>
            prev.map((m) =>
              m.id === id
                ? {
                    ...m,
                    activity: m.activity.map((s) =>
                      s.id === event.id ? { ...s, status: event.status } : s,
                    ),
                  }
                : m,
            ),
          );
          return true;
        default:
          return false;
      }
    },
    [],
  );

  // Smooth-reveal controller (typewriter drip). Instantiated once — drains
  // buffered wire tokens into the assistant bubble at a bounded char rate so the
  // text reads slower and smoother instead of jumping in bursts. See
  // `smoothReveal.ts`. `appendToAssistant`/`setAssistant` are stable (no deps).
  const revealRef = useRef<SmoothReveal | null>(null);
  useEffect(() => {
    const reveal = createSmoothReveal(
      appendToAssistant,
      (id) => setAssistant(id, ""),
      { charsPerSec: REVEAL_CHARS_PER_SEC, maxLagSec: REVEAL_MAX_LAG_SEC },
    );
    revealRef.current = reveal;
    return () => reveal.dispose();
  }, [appendToAssistant, setAssistant]);

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
      const startedAt = Date.now();
      // Finish revealing any leftover from the previous turn before retargeting.
      revealRef.current?.flush();

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
      setSuggestions([]);
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "user", content: message, activity: [], panels: [] },
        { id: assistantId, role: "assistant", content: "", activity: [], panels: [] },
      ]);
      setIsStreaming(true);

      const body: ChatRequest = {
        message,
        user_id: userId,
        trip_id: tripIdRef.current ?? null,
        conversation_id: conversationIdRef.current,
        retry: false,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
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

          const specialist = { current: null as string | null };
          for await (const event of parseSSE(res.body)) {
            if (handleActivityEvent(assistantId, event, specialist)) continue;
            switch (event.type) {
              case "start":
                // Pin the server's conversation id for turn continuity.
                conversationIdRef.current = event.conversationId;
                writeStoredConversationId(event.conversationId);
                break;
              case "token":
                received = true;
                revealRef.current?.enqueue(assistantId, event.text);
                break;
              case "reset":
                // Agent revised its answer (reflection re-ran the sub-agent) —
                // drop the superseded draft so only the final answer renders.
                // Activity/panels stay: the work still happened.
                revealRef.current?.reset(assistantId);
                break;
              case "panel": {
                received = true;
                applyPanelLanguage(event.language);
                const panel: PanelArtifact = {
                  toolCallId: event.toolCallId,
                  kind: event.kind,
                  data: event.data,
                  language: event.language,
                };
                setPanels((prev) => upsertPanelByKey(prev, panel));
                attachPanelToMessage(assistantId, panel);
                break;
              }
              case "done":
                // Terminal event — capture the turn's language for the panels.
                applyPanelLanguage(event.language);
                setSuggestions(event.suggestions);
                markPersisted(assistantId, event.assistantMessageId);
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
              // subagent / tool_call / tool_result already handled above by
              // handleActivityEvent (surfaced onto the message's activity trail).
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
          // A deliberate Stop aborts the controller too, so also run this block
          // when the user asked to stop; the unmount-cleanup abort leaves
          // userStoppedRef false and still skips it.
          if (!controller.signal.aborted || userStoppedRef.current) {
            const wasStopped = controller.signal.aborted && userStoppedRef.current;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? settleTurn(m, wasStopped, startedAt, t) : m,
              ),
            );
            setIsStreaming(false);
            // Delay onTurnComplete until after the user resolves the interrupt.
            if (!sawInterrupt) {
              onTurnComplete?.();
            }
            userStoppedRef.current = false;
          }
          if (abortRef.current === controller) abortRef.current = null;
        }
      })();
    },
    [
      applyPanelLanguage,
      attachPanelToMessage,
      handleActivityEvent,
      markPersisted,
      interrupt,
      isStreaming,
      onTurnComplete,
      t,
      userId,
    ],
  );

  const resume = useCallback(
    (approved: boolean) => {
      const assistantId = assistantIdRef.current;
      const pendingInterrupt = interrupt;
      if (!userId || !pendingInterrupt || !assistantId || inFlightRef.current)
        return;
      inFlightRef.current = true;
      const startedAt = Date.now();

      const body: ChatRequest = {
        resume: { approved },
        user_id: userId,
        trip_id: tripIdRef.current ?? null,
        conversation_id: pendingInterrupt.conversationId,
        retry: false,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      };

      setInterrupt(null);
      setIsStreaming(true);
      setError(null);
      setSuggestions([]);

      // Approval is state on the server (no reply line — it would be wiped by
      // the booking hand-off `reset`); surface it here as an activity step so
      // the trail records the decision before the booking reply streams in.
      if (approved) {
        const step: ActivityStep = {
          id: `plan-approved:${assistantId}`,
          tool: "plan_approved",
          subagent: "booking",
          status: "ok",
        };
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, activity: [...m.activity, step] } : m,
          ),
        );
      }

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

          const specialist = { current: null as string | null };
          for await (const event of parseSSE(res.body)) {
            if (handleActivityEvent(assistantId, event, specialist)) continue;
            switch (event.type) {
              case "token":
                revealRef.current?.enqueue(assistantId, event.text);
                break;
              case "reset":
                revealRef.current?.reset(assistantId);
                break;
              case "panel": {
                applyPanelLanguage(event.language);
                const panel: PanelArtifact = {
                  toolCallId: event.toolCallId,
                  kind: event.kind,
                  data: event.data,
                  language: event.language,
                };
                setPanels((prev) => upsertPanelByKey(prev, panel));
                attachPanelToMessage(assistantId, panel);
                break;
              }
              case "done":
                // Terminal event — capture the turn's language for the panels.
                applyPanelLanguage(event.language);
                setSuggestions(event.suggestions);
                markPersisted(assistantId, event.assistantMessageId);
                break;
              case "error":
                throw new Error(`agent error: ${event.code}`);
              // subagent/tool events handled above by handleActivityEvent;
              // nested interrupts and `start` are no-ops on resume.
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
          // A deliberate Stop aborts the controller too, so also run this block
          // when the user asked to stop; the unmount-cleanup abort leaves
          // userStoppedRef false and still skips it.
          if (!controller.signal.aborted || userStoppedRef.current) {
            const wasStopped = controller.signal.aborted && userStoppedRef.current;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? settleTurn(m, wasStopped, startedAt, t) : m,
              ),
            );
            setIsStreaming(false);
            onTurnComplete?.();
            userStoppedRef.current = false;
          }
          if (abortRef.current === controller) abortRef.current = null;
        }
      })();
    },
    [
      applyPanelLanguage,
      attachPanelToMessage,
      handleActivityEvent,
      markPersisted,
      interrupt,
      onTurnComplete,
      t,
      userId,
    ],
  );

  const rerun = useCallback((question: string) => {
    if (inFlightRef.current || isStreaming || interrupt !== null) return;
    if (!userId) {
      setError(t("errorIdentityNotReady"));
      return;
    }
    const conversationId = conversationIdRef.current;
    // Only meaningful on an existing conversation.
    if (!conversationId) return;
    inFlightRef.current = true;
    const startedAt = Date.now();
    // Finish revealing any leftover from the previous turn before retargeting.
    revealRef.current?.flush();

    const assistantId = newId();
    assistantIdRef.current = assistantId;
    setError(null);
    setSuggestions([]);
    // No new user bubble — the question is already on screen and in the DB.
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", activity: [], panels: [] },
    ]);
    setIsStreaming(true);

    const body: ChatRequest = {
      message: question,
      user_id: userId,
      trip_id: tripIdRef.current ?? null,
      conversation_id: conversationId,
      // Re-answer the existing user turn without re-saving the question.
      retry: true,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
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

        const specialist = { current: null as string | null };
        for await (const event of parseSSE(res.body)) {
          if (handleActivityEvent(assistantId, event, specialist)) continue;
          switch (event.type) {
            case "start":
              conversationIdRef.current = event.conversationId;
              writeStoredConversationId(event.conversationId);
              break;
            case "token":
              received = true;
              revealRef.current?.enqueue(assistantId, event.text);
              break;
            case "reset":
              revealRef.current?.reset(assistantId);
              break;
            case "panel": {
              received = true;
              applyPanelLanguage(event.language);
              const panel: PanelArtifact = {
                toolCallId: event.toolCallId,
                kind: event.kind,
                data: event.data,
                language: event.language,
              };
              setPanels((prev) => upsertPanelByKey(prev, panel));
              attachPanelToMessage(assistantId, panel);
              break;
            }
            case "done":
              // Terminal event — capture the turn's language for the panels.
              applyPanelLanguage(event.language);
              setSuggestions(event.suggestions);
              markPersisted(assistantId, event.assistantMessageId);
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
        // A deliberate Stop aborts the controller too, so also run this block
        // when the user asked to stop; the unmount-cleanup abort leaves
        // userStoppedRef false and still skips it.
        if (!controller.signal.aborted || userStoppedRef.current) {
          const wasStopped = controller.signal.aborted && userStoppedRef.current;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? settleTurn(m, wasStopped, startedAt, t) : m,
            ),
          );
          setIsStreaming(false);
          if (!sawInterrupt) {
            onTurnComplete?.();
          }
          userStoppedRef.current = false;
        }
        if (abortRef.current === controller) abortRef.current = null;
      }
    })();
  }, [
    applyPanelLanguage,
    attachPanelToMessage,
    handleActivityEvent,
    markPersisted,
    interrupt,
    isStreaming,
    onTurnComplete,
    t,
    userId,
  ]);

  const retry = useCallback(() => {
    const last = messages[messages.length - 1];
    // Only meaningful for a dangling user turn (the failed send kept the bubble).
    if (!last || last.role !== "user") return;
    rerun(last.content);
  }, [messages, rerun]);

  const regenerate = useCallback(() => {
    if (inFlightRef.current || isStreaming || interrupt !== null) return;
    const last = messages[messages.length - 1];
    const prevUser = messages[messages.length - 2];
    if (!last || last.role !== "assistant" || prevUser?.role !== "user") return;
    // Drop the answer being regenerated; the question is already on screen and
    // saved server-side, so the rerun goes out with retry: true (no re-save).
    setMessages((prev) => prev.slice(0, -1));
    rerun(prevUser.content);
  }, [interrupt, isStreaming, messages, rerun]);

  const stop = useCallback(() => {
    // Only flag a deliberate stop when there is an in-flight controller to
    // abort. Setting the flag unconditionally would leave it stale (true, with
    // nothing to reset it) if a stream had already finished between render and
    // click — a later unmount-cleanup abort would then read the stale flag and
    // wrongly run its state reset on an unmounted component.
    if (!abortRef.current) return;
    userStoppedRef.current = true;
    abortRef.current.abort();
    // The typewriter reveal buffer drains on its own rAF loop, independent of
    // the abort signal — without this it would keep visibly "typing" already
    // received text for up to its max lag after Stop. Flush (not clear) so
    // every token the server actually sent before Stop still ends up on
    // screen, just without further delay.
    revealRef.current?.flush();
  }, []);

  const newConversation = useCallback(() => {
    revealRef.current?.clear();
    clearStoredConversationId();
    conversationIdRef.current = null;
    hydratedRef.current = false;
    setMessages([]);
    setError(null);
    setInterrupt(null);
    setPanels([]);
    setPanelLanguage("en");
    setSuggestions([]);
  }, []);

  const lastMessage = messages[messages.length - 1];
  const canRetry =
    !isStreaming && interrupt === null && lastMessage?.role === "user";

  return {
    messages,
    send,
    isStreaming,
    error,
    interrupt,
    resume,
    stop,
    canRetry,
    retry,
    regenerate,
    newConversation,
    panels,
    panelLanguage,
    suggestions,
  };
}
