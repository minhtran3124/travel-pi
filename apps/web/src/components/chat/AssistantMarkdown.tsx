"use client";

import { Streamdown } from "streamdown";

import { cn } from "@/lib/cn";

export interface AssistantMarkdownProps {
  content: string;
  /** True while this message is still streaming in — drives incomplete-markdown repair. */
  isStreaming: boolean;
}

/**
 * Renders streamed assistant markdown. Streamdown handles GitHub-flavored
 * markdown plus the streaming-specific hard part — `parseIncompleteMarkdown`
 * (on by default) styles unterminated bold/fences/lists mid-stream so tokens
 * never flash as raw `**text**`, and completed blocks are memoized so new
 * tokens don't re-parse the whole message.
 *
 * Untrusted agent output is safe by default: Streamdown escapes raw HTML (we
 * never enable dangerous HTML) and hardens links.
 */
export function AssistantMarkdown({ content, isStreaming }: AssistantMarkdownProps) {
  return (
    <Streamdown
      isAnimating={isStreaming}
      className={cn(
        "text-sm leading-relaxed",
        // tighten Streamdown's default block spacing inside the chat bubble
        "[&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
        // Streamdown's default heading sizes dwarf the bubble text — scale them
        // down to a chat-appropriate hierarchy just above body size.
        "[&_h1]:text-lg [&_h2]:text-base [&_h3]:text-sm [&_h4]:text-sm [&_h5]:text-sm [&_h6]:text-sm",
        "[&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold",
      )}
    >
      {content}
    </Streamdown>
  );
}
