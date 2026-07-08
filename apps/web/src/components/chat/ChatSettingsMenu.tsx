"use client";

import { useEffect, useRef, useState } from "react";

import { useTranslations } from "next-intl";

const iconButtonClass =
  "flex h-9 w-9 items-center justify-center rounded-[12px] border border-line bg-panel text-ink transition duration-150 hover:bg-panel-raised active:translate-y-px";

export interface ChatSettingsMenuProps {
  /** Start a fresh conversation (caller decides whether to confirm first). */
  onNewConversation: () => void;
  disabled?: boolean;
}

/**
 * Top-right chat settings control: a gear button that opens a small dropdown.
 * For now the only action is "New conversation". Mirrors the open/close +
 * click-outside + Escape behaviour of {@link ../auth/UserMenu}.
 */
export function ChatSettingsMenu({
  onNewConversation,
  disabled = false,
}: ChatSettingsMenuProps) {
  const t = useTranslations("Chat");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("settingsMenu")}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className={iconButtonClass}
      >
        <svg
          width={18}
          height={18}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-sm w-[13rem] overflow-hidden rounded-md border border-line bg-panel shadow-lift"
        >
          <button
            type="button"
            role="menuitem"
            aria-label={t("newConversation")}
            onClick={() => {
              setOpen(false);
              onNewConversation();
            }}
            className="flex w-full items-center gap-sm px-md py-sm text-left text-sm font-medium text-ink transition hover:bg-panel-raised"
          >
            <svg
              width={15}
              height={15}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              className="shrink-0 text-muted"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>
            {t("newConversation")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
