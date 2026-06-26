"use client";

import { useState } from "react";

/**
 * STUB: launcher FAB only. The real chat widget replaces this in a later task.
 * Clicking toggles a "coming soon" tooltip; no chat surface yet.
 */
export function ChatWidget() {
  const [showHint, setShowHint] = useState(false);

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-sm">
      {showHint ? (
        <p
          role="status"
          className="rounded-md bg-panel-raised px-md py-sm text-sm font-semibold text-ink shadow-card"
        >
          Chat is coming soon
        </p>
      ) : null}
      <button
        type="button"
        aria-label="Open travel chat"
        onClick={() => setShowHint((v) => !v)}
        className="flex h-14 w-14 items-center justify-center rounded-pill bg-lime text-void shadow-lift transition hover:brightness-110 active:translate-y-px"
      >
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
      </button>
    </div>
  );
}
