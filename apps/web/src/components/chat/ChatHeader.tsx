"use client";

import { useTranslations } from "next-intl";

import { cn } from "@/lib/cn";
import { AgentAvatar } from "./AgentAvatar";

const iconButtonClass =
  "flex h-9 w-9 items-center justify-center rounded-[12px] border border-line bg-panel text-ink transition duration-150 hover:bg-panel-raised active:translate-y-px";

const svgProps = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export type AgentStatus = "ready" | "working" | "waiting";

const STATUS_KEY: Record<AgentStatus, string> = {
  ready: "statusReady",
  working: "statusWorking",
  waiting: "statusWaiting",
};

const STATUS_DOT: Record<AgentStatus, string> = {
  ready: "bg-status-confirmed",
  working: "bg-lime",
  waiting: "bg-status-estimated",
};

export interface ChatHeaderProps {
  status: AgentStatus;
  fullscreen: boolean;
  onToggleFullscreen: () => void;
  onClose: () => void;
}

/** Chat panel title bar: agent identity, live status, expand/shrink + close. */
export function ChatHeader({
  status,
  fullscreen,
  onToggleFullscreen,
  onClose,
}: ChatHeaderProps) {
  const t = useTranslations("Chat");
  return (
    <header className="flex items-center justify-between border-b border-line bg-gradient-to-r from-lime-soft/55 via-panel to-panel px-lg py-md">
      <div className="flex items-center gap-sm">
        <AgentAvatar size="sm" />
        <div className="leading-tight">
          <h2 className="text-sm font-bold tracking-tight text-ink">
            {t("headerTitle")}
          </h2>
          <p
            role="status"
            aria-live="polite"
            className="flex items-center gap-1.5 text-xs text-muted"
          >
            <span
              aria-hidden="true"
              className={cn(
                "h-1.5 w-1.5 rounded-pill",
                STATUS_DOT[status],
                status === "working" && "tp-typing-dot",
              )}
            />
            {t(STATUS_KEY[status])}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-xs">
        <button
          type="button"
          aria-label={fullscreen ? t("shrinkPanel") : t("expandPanel")}
          aria-pressed={fullscreen}
          onClick={onToggleFullscreen}
          className={iconButtonClass}
        >
          <svg {...svgProps}>
            {fullscreen ? (
              <path d="M9 9 4 4m0 0v4m0-4h4m6 5 5-5m0 0v4m0-4h-4M9 15l-5 5m0 0v-4m0 4h4m6-5 5 5m0 0v-4m0 4h-4" />
            ) : (
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
            )}
          </svg>
        </button>
        <button
          type="button"
          aria-label={t("closeAssistant")}
          onClick={onClose}
          className={iconButtonClass}
        >
          <svg {...svgProps}>
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </header>
  );
}
