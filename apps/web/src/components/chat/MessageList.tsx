"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/cn";
import { Spinner } from "@/components/ui/Spinner";
import type { ChatMessage } from "./useAgentStream";

export interface MessageListProps {
  messages: ChatMessage[];
  isStreaming: boolean;
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
            className={isUser ? "flex justify-end" : "flex justify-start"}
          >
            <div
              className={cn(
                "max-w-[80%] whitespace-pre-wrap rounded-[16px] px-md py-sm text-sm",
                isUser
                  ? "bg-[#1c1c1c] font-medium text-white"
                  : "bg-[#f4f4f2] text-[#1c1c1c]",
              )}
            >
              {streamingEmpty ? <Spinner label="Assistant is typing" /> : m.content}
            </div>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
