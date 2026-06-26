"use client";

import { useState } from "react";

export interface ChatComposerProps {
  /** Blocks input while a turn is streaming or an interrupt is pending. */
  disabled: boolean;
  onSend: (text: string) => void;
}

/** Message input + send button. Owns its own draft state. */
export function ChatComposer({ disabled, onSend }: ChatComposerProps) {
  const [draft, setDraft] = useState("");

  const submit = () => {
    const text = draft.trim();
    if (text.length === 0 || disabled) return;
    onSend(text);
    setDraft("");
  };

  return (
    <form
      className="border-t border-[#ececec] bg-white px-lg py-md"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="flex items-center gap-sm rounded-pill border border-[#ececec] bg-[#f7f7f5] py-1 pl-md pr-1">
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="shrink-0 text-[#9a9a9a]"
          aria-hidden="true"
        >
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
        </svg>
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Message the travel assistant…"
          aria-label="Message"
          className="min-w-0 flex-1 bg-transparent text-sm text-[#1c1c1c] placeholder:text-[#9a9a9a] focus:outline-none"
        />
        <button
          type="submit"
          aria-label="Send message"
          disabled={disabled || draft.trim().length === 0}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-pill bg-[#1c1c1c] text-white transition hover:brightness-125 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
          </svg>
        </button>
      </div>
    </form>
  );
}
