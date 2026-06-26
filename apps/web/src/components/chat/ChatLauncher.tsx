"use client";

import { useTranslations } from "next-intl";

export interface ChatLauncherProps {
  open: boolean;
  onToggle: () => void;
}

/**
 * Bottom-right circular lime FAB toggling the chat panel (chat icon ⇄ ×). The
 * agent's single most expressive use of the accent — it waves hello with a soft
 * ring pulse on mount, then rests. (Reduced-motion silences the pulse.)
 */
export function ChatLauncher({ open, onToggle }: ChatLauncherProps) {
  const t = useTranslations("Chat");
  return (
    <span className="relative flex h-14 w-14 items-center justify-center">
      {!open ? (
        <span
          aria-hidden="true"
          className="tp-ping pointer-events-none absolute inset-0 rounded-pill bg-lime"
        />
      ) : null}
      <button
        type="button"
        aria-label={open ? t("closeAssistant") : t("openAssistant")}
        aria-expanded={open}
        onClick={onToggle}
        className="relative flex h-14 w-14 items-center justify-center rounded-pill bg-lime text-ink shadow-lift transition duration-150 hover:brightness-105 hover:scale-105 active:translate-y-px active:scale-100"
      >
        <span
          className="transition-transform duration-200 ease-out"
          style={{ transform: open ? "rotate(90deg)" : "none" }}
        >
          {open ? (
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          ) : (
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
            </svg>
          )}
        </span>
      </button>
    </span>
  );
}
