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
        disabled={disabled || draft.trim().length === 0}
        className="flex h-9 items-center justify-center rounded-sm bg-lime px-md text-sm font-bold text-void transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Send
      </button>
    </form>
  );
}
