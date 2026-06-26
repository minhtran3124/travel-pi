"use client";

import { useState } from "react";

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
 */
export function ChatPanel({ stream, onClose }: ChatPanelProps) {
  const { messages, send, isStreaming, error } = stream;
  const [draft, setDraft] = useState("");
  const [fullscreen, setFullscreen] = useState(false);

  const submit = () => {
    const text = draft.trim();
    if (text.length === 0 || isStreaming) return;
    send(text);
    setDraft("");
  };

  return (
    <section
      role="dialog"
      aria-label="Travel Assistant"
      className={[
        "flex flex-col overflow-hidden rounded-md border border-lime/30 bg-void text-ink shadow-lift",
        fullscreen
          ? "h-[80vh] w-[min(92vw,640px)]"
          : "h-[min(70vh,560px)] w-[min(92vw,400px)]",
      ].join(" ")}
    >
      <header className="flex items-center justify-between border-b border-line bg-panel px-lg py-md">
        <div className="flex items-center gap-sm">
          <span className="h-2 w-2 rounded-pill bg-lime" aria-hidden="true" />
          <h2 className="text-sm font-bold tracking-tight text-ink">
            Travel Assistant
          </h2>
        </div>
        <div className="flex items-center gap-xs">
          <button
            type="button"
            aria-label={fullscreen ? "Shrink panel" : "Expand panel"}
            aria-pressed={fullscreen}
            onClick={() => setFullscreen((v) => !v)}
            className="rounded-sm p-1 text-muted transition hover:text-lime"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              {fullscreen ? (
                <path d="M9 9 4 4m0 0v4m0-4h4m6 5 5-5m0 0v4m0-4h-4M9 15l-5 5m0 0v-4m0 4h4m6-5 5 5m0 0v-4m0 4h-4" />
              ) : (
                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              )}
            </svg>
          </button>
          <button
            type="button"
            aria-label="Close travel assistant"
            onClick={onClose}
            className="rounded-sm p-1 text-muted transition hover:text-lime"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </header>

      {error ? (
        <p
          role="status"
          className="border-b border-amber-400/30 bg-amber-400/10 px-lg py-sm text-xs font-medium text-amber-300"
        >
          {error}
        </p>
      ) : null}

      {messages.length === 0 ? (
        <div className="px-lg py-md">
          <p className="text-sm text-muted">
            Hi! I&apos;m your travel co-pilot. Ask me to plan a trip, find places,
            or check the weather.
          </p>
        </div>
      ) : null}

      <MessageList messages={messages} isStreaming={isStreaming} />

      {messages.length === 0 ? (
        <QuickReplies onPick={send} disabled={isStreaming} />
      ) : null}

      <form
        className="flex items-center gap-sm border-t border-line bg-panel px-lg py-md"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Message the travel assistant…"
          aria-label="Message"
          className="min-w-0 flex-1 rounded-sm border border-line bg-void px-md py-sm text-sm text-ink placeholder:text-muted focus:border-lime"
        />
        <button
          type="submit"
          aria-label="Send message"
          disabled={isStreaming || draft.trim().length === 0}
          className="flex h-9 items-center justify-center rounded-sm bg-lime px-md text-sm font-bold text-void transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </section>
  );
}
