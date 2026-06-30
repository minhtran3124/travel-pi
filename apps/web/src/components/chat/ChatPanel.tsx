"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { cn } from "@/lib/cn";
import { ChatComposer } from "./ChatComposer";
import { ChatEmptyState } from "./ChatEmptyState";
import { ChatHeader, type AgentStatus } from "./ChatHeader";
import { InterruptPrompt } from "./InterruptPrompt";
import { MessageList } from "./MessageList";
import type { ChatMode, UseAgentStream } from "./useAgentStream";

export interface ChatPanelProps {
  stream: UseAgentStream;
  onClose: () => void;
  /** True when the agent has emitted at least one renderable side-panel. */
  hasPanels?: boolean;
  /** Whether the side-panel drawer is currently collapsed. */
  mapHidden?: boolean;
  /** Toggle the side-panel drawer open/closed. */
  onToggleMap?: () => void;
}

/**
 * The agent's surface: a floating white panel that springs out of the launcher,
 * carrying the agent's identity + live status, a teaching empty state, the
 * streaming transcript, and a composer. Surfaces an amber notice when the agent
 * has degraded/failed.
 *
 * When the agent emits an interrupt event (HITL plan approval), an inline
 * approve/reject checkpoint replaces the composer until the user decides.
 */
const MODES: ChatMode[] = ["fast", "balanced", "deep"];

export function ChatPanel({
  stream,
  onClose,
  hasPanels = false,
  mapHidden = false,
  onToggleMap,
}: ChatPanelProps) {
  const t = useTranslations("Chat");
  const { messages, send, isStreaming, error, interrupt, resume, canRetry, retry, mode, setMode } =
    stream;
  const [fullscreen, setFullscreen] = useState(false);

  const inputBlocked = isStreaming || interrupt !== null;
  const status: AgentStatus =
    interrupt !== null ? "waiting" : isStreaming ? "working" : "ready";

  return (
    <section
      role="dialog"
      aria-label={t("dialogLabel")}
      className={cn(
        "tp-chat-in flex flex-col overflow-hidden rounded-[20px] border border-line bg-panel text-ink shadow-lift",
        fullscreen
          ? "h-[80vh] w-[min(92vw,640px)]"
          : "h-[min(70vh,560px)] w-[min(92vw,400px)]",
      )}
    >
      <ChatHeader
        status={status}
        fullscreen={fullscreen}
        onToggleFullscreen={() => setFullscreen((v) => !v)}
        onClose={onClose}
      />

      <div className="flex items-center gap-sm border-b border-line bg-surface px-lg py-sm">
        <label htmlFor="chat-mode" className="shrink-0 text-xs font-medium text-muted">
          {t("modeLabel")}
        </label>
        <div className="relative inline-flex items-center">
          <select
            id="chat-mode"
            value={mode}
            onChange={(e) => setMode(e.target.value as ChatMode)}
            aria-label={t("modeLabel")}
            className={cn(
              "appearance-none rounded-pill border border-line bg-panel-raised",
              "py-1 pl-md pr-7 text-xs font-semibold text-ink",
              "cursor-pointer transition-colors hover:border-ink hover:bg-panel",
            )}
          >
            {MODES.map((m) => (
              <option key={m} value={m}>
                {t(`mode${m.charAt(0).toUpperCase()}${m.slice(1)}` as "modeFast" | "modeBalanced" | "modeDeep")}
              </option>
            ))}
          </select>
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            className="pointer-events-none absolute right-2.5 size-3 text-muted"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </div>
      </div>

      {error ? (
        <p
          role="status"
          className="border-b border-status-estimated/30 bg-status-estimated/10 px-lg py-sm text-xs font-medium text-status-estimated"
        >
          {error}
        </p>
      ) : null}

      {messages.length === 0 ? (
        <ChatEmptyState onPick={send} disabled={inputBlocked} />
      ) : (
        <MessageList messages={messages} isStreaming={isStreaming} />
      )}

      {canRetry ? (
        <div className="flex items-center justify-between gap-sm border-t border-line bg-panel-raised px-lg py-sm">
          <span className="text-xs text-muted">{t("retryHint")}</span>
          <button
            type="button"
            onClick={retry}
            className="shrink-0 rounded-pill border border-line px-md py-1 text-xs font-medium text-ink transition hover:bg-line/40"
          >
            {t("retry")}
          </button>
        </div>
      ) : null}

      {hasPanels && onToggleMap ? (
        <div className="flex justify-start border-t border-line bg-surface px-lg py-sm">
          <button
            type="button"
            onClick={onToggleMap}
            className="rounded-pill border border-line px-md py-1 text-xs font-medium text-ink transition hover:bg-line/40"
          >
            {mapHidden ? "Show panel" : "Hide panel"}
          </button>
        </div>
      ) : null}

      {interrupt !== null ? (
        <InterruptPrompt
          draft={interrupt.payload.draft}
          onApprove={() => resume(true)}
          onReject={() => resume(false)}
        />
      ) : (
        <ChatComposer disabled={inputBlocked} onSend={send} />
      )}
    </section>
  );
}
