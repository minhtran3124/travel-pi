"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/cn";

const COPIED_RESET_MS = 1500;

const svgProps = {
  width: 15,
  height: 15,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

/** Ghost icon button — must not compete with the composer's send button. */
const ghostButtonClass =
  "flex h-7 w-7 items-center justify-center rounded-[10px] text-muted transition duration-150 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50";

export interface MessageActionsProps {
  content: string;
  onRegenerate?: () => void;
  disabled?: boolean;
}

/** Per-message affordance row: copy the reply, optionally regenerate it. */
export function MessageActions({
  content,
  onRegenerate,
  disabled,
}: MessageActionsProps) {
  const t = useTranslations("Chat");
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    },
    [],
  );

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content);
    } catch {
      // Clipboard API unavailable or rejected — degrade silently.
      return;
    }
    setCopied(true);
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => setCopied(false), COPIED_RESET_MS);
  }, [content]);

  const copyLabel = copied ? t("actions.copied") : t("actions.copy");

  return (
    <div className="flex items-center gap-xs">
      <button
        type="button"
        aria-label={copyLabel}
        disabled={disabled}
        onClick={handleCopy}
        className={cn(ghostButtonClass, copied && "text-status-confirmed")}
      >
        {copied ? (
          <svg {...svgProps}>
            <path d="M20 6 9 17l-5-5" />
          </svg>
        ) : (
          <svg {...svgProps}>
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
        )}
      </button>
      {onRegenerate ? (
        <button
          type="button"
          aria-label={t("actions.regenerate")}
          disabled={disabled}
          onClick={onRegenerate}
          className={ghostButtonClass}
        >
          <svg {...svgProps}>
            <path d="M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6" />
          </svg>
        </button>
      ) : null}
    </div>
  );
}
