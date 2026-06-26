"use client";

export interface ChatLauncherProps {
  open: boolean;
  onToggle: () => void;
}

/** Bottom-right circular lime FAB toggling the chat panel (chat icon ⇄ ×). */
export function ChatLauncher({ open, onToggle }: ChatLauncherProps) {
  return (
    <button
      type="button"
      aria-label={open ? "Close travel assistant" : "Open travel assistant"}
      aria-expanded={open}
      onClick={onToggle}
      className="flex h-14 w-14 items-center justify-center rounded-pill bg-lime text-void shadow-lift transition hover:brightness-110 active:translate-y-px"
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
    </button>
  );
}
