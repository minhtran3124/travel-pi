"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

export function Modal({ open, onClose, title, children }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#1c1c1c]/40 p-lg backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        // NOTE: `max-w-md` is unusable here — this project's `@theme` defines
        // `--spacing-md`, which Tailwind v4 resolves ahead of the container scale
        // for `max-w-*`, collapsing `max-w-md` to 12px. Use the explicit width.
        className="w-full max-w-[28rem] rounded-lg border border-line bg-panel p-lg shadow-lift [animation:tp-pop_0.16s_ease-out]"
        onClick={(e) => e.stopPropagation()}
      >
        {title ? (
          <h2 className="mb-md text-[1.1rem] font-extrabold text-ink">{title}</h2>
        ) : null}
        {children}
      </div>
    </div>
  );
}
