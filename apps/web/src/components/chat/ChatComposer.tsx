"use client";

import { useTranslations } from "next-intl";
import { useLayoutEffect, useRef, useState } from "react";

export interface ChatComposerProps {
  /** Blocks input while a turn is streaming or an interrupt is pending. */
  disabled: boolean;
  onSend: (text: string) => void;
}

const MAX_TEXTAREA_HEIGHT = 120; // ~5 lines, then it scrolls

/** Auto-growing message input + send button. Owns its own draft state. */
export function ChatComposer({ disabled, onSend }: ChatComposerProps) {
  const t = useTranslations("Chat");
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Grow the textarea with its content, capped, then scroll.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [draft]);

  const canSend = draft.trim().length > 0 && !disabled;

  const submit = () => {
    if (!canSend) return;
    onSend(draft.trim());
    setDraft("");
  };

  return (
    <form
      className="border-t border-line bg-panel px-lg py-md"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="flex items-end gap-sm rounded-[18px] border border-line bg-void p-1.5 pl-md transition focus-within:border-faint focus-within:shadow-card">
        <textarea
          ref={textareaRef}
          rows={1}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter inserts a newline.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={t("composerPlaceholder")}
          aria-label={t("composerAriaLabel")}
          className="min-w-0 flex-1 resize-none self-center bg-transparent py-1.5 text-sm leading-relaxed text-ink placeholder:text-muted focus:outline-none focus-visible:shadow-none"
        />
        <button
          type="submit"
          aria-label={t("sendMessage")}
          disabled={!canSend}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-pill bg-ink text-on-ink transition duration-150 hover:bg-ink-hover active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-ink"
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
