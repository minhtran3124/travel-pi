"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { cn } from "@/lib/cn";
import { ChatComposer } from "./ChatComposer";
import { ChatEmptyState } from "./ChatEmptyState";
import { ChatHeader, type AgentStatus } from "./ChatHeader";
import { ChatSuggestions } from "./ChatSuggestions";
import { InterruptPrompt } from "./InterruptPrompt";
import { MessageList } from "./MessageList";
import type { UseAgentStream } from "./useAgentStream";

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
export function ChatPanel({
  stream,
  onClose,
  hasPanels = false,
  mapHidden = false,
  onToggleMap,
}: ChatPanelProps) {
  const t = useTranslations("Chat");
  const {
    messages,
    send,
    isStreaming,
    error,
    interrupt,
    resume,
    canRetry,
    retry,
    suggestions,
  } = stream;
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

      {messages.length > 0 && !isStreaming && interrupt === null && suggestions.length > 0 ? (
        <ChatSuggestions suggestions={suggestions} onPick={send} disabled={inputBlocked} />
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
