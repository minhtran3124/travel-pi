"use client";

export interface InterruptPromptProps {
  /** The agent's pending draft (e.g. the booking it wants to confirm). */
  draft: string;
  onApprove: () => void;
  onReject: () => void;
}

/** HITL approve/reject prompt shown in place of the composer during an interrupt. */
export function InterruptPrompt({
  draft,
  onApprove,
  onReject,
}: InterruptPromptProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="border-t border-line bg-panel px-lg py-md"
    >
      <p className="mb-sm text-xs font-medium text-muted">Ready to book:</p>
      <p className="mb-md text-sm text-ink">{draft}</p>
      <div className="flex gap-sm">
        <button
          type="button"
          onClick={onApprove}
          className="flex-1 rounded-sm bg-lime px-md py-sm text-sm font-bold text-void transition hover:brightness-110"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={onReject}
          className="flex-1 rounded-sm border border-line bg-panel-raised px-md py-sm text-sm font-medium text-muted transition hover:text-ink"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
