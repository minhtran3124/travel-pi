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
      className="border-t border-[#ececec] bg-white px-lg py-md"
    >
      <p className="mb-sm text-xs font-medium text-[#6b6b6b]">Ready to book:</p>
      <p className="mb-md text-sm text-[#1c1c1c]">{draft}</p>
      <div className="flex gap-sm">
        <button
          type="button"
          onClick={onApprove}
          className="flex-1 rounded-pill bg-[#1c1c1c] px-md py-sm text-sm font-bold text-white transition hover:brightness-125"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={onReject}
          className="flex-1 rounded-pill border border-[#ececec] bg-white px-md py-sm text-sm font-medium text-[#6b6b6b] transition hover:bg-[#f4f4f2] hover:text-[#1c1c1c]"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
