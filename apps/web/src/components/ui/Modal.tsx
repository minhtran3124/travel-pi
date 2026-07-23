"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Modal({ open, onClose, title, children }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  // Read onClose through a ref so the focus effect depends only on `open` —
  // otherwise a fresh onClose identity on every parent render re-runs the
  // effect and yanks focus back to the first field while the user is typing.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;

    // Move focus into the dialog on open (first control, else the dialog).
    const initial = dialog?.querySelectorAll<HTMLElement>(FOCUSABLE)[0];
    (initial ?? dialog)?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !dialog) return;
      const items = dialog.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-scrim/40 p-lg backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        // NOTE: `max-w-md` is unusable here — this project's `@theme` defines
        // `--spacing-md`, which Tailwind v4 resolves ahead of the container scale
        // for `max-w-*`, collapsing `max-w-md` to 12px. Use the explicit width.
        className="w-full max-w-[28rem] rounded-lg border border-line bg-panel p-lg shadow-lift outline-none [animation:tp-pop_0.16s_ease-out]"
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
