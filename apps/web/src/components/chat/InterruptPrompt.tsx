"use client";

import { useTranslations } from "next-intl";

export interface InterruptPromptProps {
  /** The agent's pending draft (e.g. the booking it wants to confirm). */
  draft: string;
  onApprove: () => void;
  onReject: () => void;
}

/**
 * HITL checkpoint shown in place of the composer during an interrupt. Lime marks
 * the moment the agent hands control back — the "in control, never managed"
 * principle made visible — and nothing happens until the user decides.
 */
export function InterruptPrompt({
  draft,
  onApprove,
  onReject,
}: InterruptPromptProps) {
  const t = useTranslations("Chat");
  return (
    <div
      role="status"
      aria-live="polite"
      className="tp-msg-in border-t border-line bg-lime-soft/40 px-lg py-md"
    >
      <div className="mb-sm flex items-center gap-sm">
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-pill bg-lime text-ink">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
        <p className="text-sm font-bold text-ink">{t("interruptTitle")}</p>
      </div>
      <p className="mb-md text-sm leading-relaxed text-ink">{draft}</p>
      <div className="flex gap-sm">
        <button
          type="button"
          onClick={onApprove}
          className="flex-1 rounded-sm bg-ink px-md py-sm text-sm font-bold text-white transition duration-150 hover:bg-[#2e2e2e] active:translate-y-px"
        >
          {t("approve")}
        </button>
        <button
          type="button"
          onClick={onReject}
          className="flex-1 rounded-sm border border-line bg-white px-md py-sm text-sm font-medium text-muted transition duration-150 hover:bg-panel-raised hover:text-ink active:translate-y-px"
        >
          {t("reject")}
        </button>
      </div>
    </div>
  );
}
