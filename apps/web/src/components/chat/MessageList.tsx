"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/cn";
import type { PanelArtifact } from "@/lib/stream/panel";
import { AgentActivityTrail } from "./AgentActivityTrail";
import { AgentAvatar } from "./AgentAvatar";
import { AssistantMarkdown } from "./AssistantMarkdown";
import { MessageActions } from "./MessageActions";
import { MessageFeedback } from "./MessageFeedback";
import { ResultChips } from "./ResultChips";
import type { ChatMessage } from "./useAgentStream";

export interface MessageListProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  /** Promote an inline result card to the full renderer (drawer / sheet). */
  onOpenPanel?: (panel: PanelArtifact) => void;
  /** Re-run the last turn; wired only to the last assistant message. */
  onRegenerate?: () => void;
}

/** Stable no-op so a missing `onOpenPanel` keeps `ResultChips`'s required prop satisfied. */
const noopOpen = () => {};

/** Three bouncing dots — the agent "thinking" before its first token lands. */
function TypingDots() {
  const t = useTranslations("Chat");
  return (
    <span className="flex items-center gap-1 py-0.5" aria-label={t("typingAria")}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="tp-typing-dot h-1.5 w-1.5 rounded-pill bg-muted"
          style={{ animationDelay: `${i * 160}ms` }}
        />
      ))}
    </span>
  );
}

/** Scrollable transcript of user/assistant bubbles; assistant streams in. */
export function MessageList({
  messages,
  isStreaming,
  onOpenPanel,
  onRegenerate,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, isStreaming]);

  // The last assistant message is the only one that can still be streaming and
  // the only one whose actions offer Regenerate (re-runs the last turn).
  let lastAssistantIndex = -1;
  messages.forEach((m, i) => {
    if (m.role === "assistant") lastAssistantIndex = i;
  });

  return (
    <div className="flex flex-1 flex-col gap-md overflow-y-auto px-lg py-md">
      {messages.map((m, i) => {
        if (m.role === "user") {
          return (
            <div
              key={m.id}
              className="tp-msg-in flex items-end justify-end gap-sm"
            >
              <div className="max-w-[78%] whitespace-pre-wrap rounded-[16px] rounded-br-[5px] bg-ink px-md py-sm text-sm font-medium leading-normal text-on-ink">
                {m.content}
              </div>
            </div>
          );
        }

        const isLastAssistant = i === lastAssistantIndex;
        const streaming = isLastAssistant && isStreaming;
        const streamingEmpty = streaming && m.content.length === 0;
        // No first token yet: keep TypingDots only when the turn used no tools;
        // once steps exist the trail carries the "working" signal in its place.
        const showTypingDots = streamingEmpty && m.activity.length === 0;
        const showBubble = !streamingEmpty || showTypingDots;

        return (
          <div key={m.id} className="tp-msg-in flex flex-col gap-xs">
            <AgentActivityTrail
              steps={m.activity}
              isStreaming={streaming}
              elapsedMs={m.elapsedMs}
              onRetry={isLastAssistant ? onRegenerate : undefined}
            />
            {showBubble ? (
              <div className="flex items-end justify-start gap-sm">
                <AgentAvatar size="sm" className="mb-0.5" />
                <div
                  className={cn(
                    "max-w-[78%] rounded-[16px] rounded-bl-[5px] border border-line bg-panel px-md py-sm text-sm leading-normal text-ink shadow-card",
                  )}
                >
                  {showTypingDots ? (
                    <TypingDots />
                  ) : (
                    <div className="flex items-start gap-xs">
                      {streaming ? (
                        <span
                          aria-hidden="true"
                          className="tp-trail-dot mt-2 h-1.5 w-1.5 shrink-0 rounded-pill bg-lime"
                        />
                      ) : null}
                      <AssistantMarkdown content={m.content} isStreaming={streaming} />
                    </div>
                  )}
                </div>
              </div>
            ) : null}
            {/* Panel events arrive on the wire BEFORE the answer's tokens (tools
                run first), so revealing chips mid-stream shows results above an
                empty bubble. Hold them until the turn finishes streaming — the
                same moment MessageActions appears — so the reading order stays
                text first, then the entry points to details. */}
            {!streaming && m.panels.length > 0 ? (
              <ResultChips panels={m.panels} onOpen={onOpenPanel ?? noopOpen} />
            ) : null}
            {!streaming && m.content.trim().length > 0 ? (
              <MessageActions
                content={m.content}
                onRegenerate={isLastAssistant ? onRegenerate : undefined}
              />
            ) : null}
            {/* Only a complete turn with a persisted id is rateable (DESIGN
                §7.1): streaming, interrupted, stopped and failed turns never
                receive a `serverMessageId`. */}
            {!streaming && m.serverMessageId ? (
              <MessageFeedback
                assistantMessageId={m.serverMessageId}
                initial={m.feedback}
              />
            ) : null}
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
