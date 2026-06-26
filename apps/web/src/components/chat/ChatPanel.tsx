"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";
import { ChatComposer } from "./ChatComposer";
import { ChatHeader } from "./ChatHeader";
import { InterruptPrompt } from "./InterruptPrompt";
import { MessageList } from "./MessageList";
import { QuickReplies } from "./QuickReplies";
import type { UseAgentStream } from "./useAgentStream";

export interface ChatPanelProps {
  stream: UseAgentStream;
  onClose: () => void;
}

/**
 * Dark Kith-style overlay: lime-accented surface with a header, greeting,
 * quick-reply chips, the streaming transcript, and a composer. Surfaces an
 * amber notice when the agent has degraded/failed.
 *
 * When the agent emits an interrupt event (HITL plan approval), an inline
 * approve/reject prompt replaces the composer until the user decides.
 */
export function ChatPanel({ stream, onClose }: ChatPanelProps) {
  const { messages, send, isStreaming, error, interrupt, resume } = stream;
  const [fullscreen, setFullscreen] = useState(false);

  const inputBlocked = isStreaming || interrupt !== null;

  return (
    <section
      role="dialog"
      aria-label="Travel Assistant"
      className={cn(
        "flex flex-col overflow-hidden rounded-[20px] border border-[#ececec] bg-white text-[#1c1c1c] shadow-lift",
        fullscreen
          ? "h-[80vh] w-[min(92vw,640px)]"
          : "h-[min(70vh,560px)] w-[min(92vw,400px)]",
      )}
    >
      <ChatHeader
        fullscreen={fullscreen}
        onToggleFullscreen={() => setFullscreen((v) => !v)}
        onClose={onClose}
      />

      {error ? (
        <p
          role="status"
          className="border-b border-amber-200 bg-amber-50 px-lg py-sm text-xs font-medium text-amber-700"
        >
          {error}
        </p>
      ) : null}

      {messages.length === 0 ? (
        <div className="px-lg py-md">
          <p className="text-sm text-[#6b6b6b]">
            Hi! I&apos;m your travel co-pilot. Ask me to plan a trip, find places,
            or check the weather.
          </p>
        </div>
      ) : null}

      <MessageList messages={messages} isStreaming={isStreaming} />

      {messages.length === 0 ? (
        <QuickReplies onPick={send} disabled={inputBlocked} />
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
