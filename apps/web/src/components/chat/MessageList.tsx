"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/cn";
import { AgentAvatar } from "./AgentAvatar";
import { AssistantMarkdown } from "./AssistantMarkdown";
import type { ChatMessage } from "./useAgentStream";

export interface MessageListProps {
  messages: ChatMessage[];
  isStreaming: boolean;
}

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
export function MessageList({ messages, isStreaming }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, isStreaming]);

  return (
    <div className="flex flex-1 flex-col gap-md overflow-y-auto px-lg py-md">
      {messages.map((m) => {
        const isUser = m.role === "user";
        const streamingEmpty =
          !isUser && m.content.length === 0 && isStreaming;
        return (
          <div
            key={m.id}
            className={cn(
              "tp-msg-in flex items-end gap-sm",
              isUser ? "justify-end" : "justify-start",
            )}
          >
            {!isUser ? <AgentAvatar size="sm" className="mb-0.5" /> : null}
            <div
              className={cn(
                "max-w-[78%] px-md py-sm text-sm leading-relaxed",
                isUser
                  ? "whitespace-pre-wrap rounded-[16px] rounded-br-[5px] bg-ink font-medium text-white"
                  : "rounded-[16px] rounded-bl-[5px] border border-line bg-white text-ink shadow-card",
              )}
            >
              {isUser ? (
                m.content
              ) : streamingEmpty ? (
                <TypingDots />
              ) : (
                <AssistantMarkdown content={m.content} isStreaming={isStreaming} />
              )}
            </div>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
