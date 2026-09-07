"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";


export interface ChatEmptyStateProps {
  onPick: (text: string) => void;
  disabled?: boolean;
}

interface Capability {
  /** `capabilities.*` key holding the tile's `label` + `subtitle`. */
  key: string;
  /** Translation key for the natural-language prompt sent to the agent. */
  promptKey: string;
  icon: ReactNode;
}

/**
 * First-run state for the chat. Instead of leaking internal tool names, it
 * greets the user in the well-traveled-friend voice and offers a 2×2 grid of
 * real agent capabilities (plan / find nearby / weather / budget). Each tile
 * dispatches the same curated starter prompt the old vertical list used.
 */
const CAPABILITIES: Capability[] = [
  {
    key: "plan",
    promptKey: "suggestions.planWeekendPrompt",
    icon: (
      <path d="M12 2l1.9 5.1L19 9l-5.1 1.9L12 16l-1.9-5.1L5 9l5.1-1.9L12 2z" />
    ),
  },
  {
    key: "nearby",
    promptKey: "suggestions.findCoffeePrompt",
    icon: (
      <path d="M21 10c0 6-4 11-9 11s-9-5-9-11a9 9 0 0 1 18 0zM12 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
    ),
  },
  {
    key: "weather",
    promptKey: "suggestions.checkWeatherPrompt",
    icon: (
      <path d="M12 3v2m0 14v2M5.6 5.6l1.4 1.4m10 10 1.4 1.4M3 12h2m14 0h2M5.6 18.4l1.4-1.4m10-10 1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" />
    ),
  },
  {
    key: "budget",
    promptKey: "suggestions.checkBudgetPrompt",
    icon: (
      <path d="M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    ),
  },
];

export function ChatEmptyState({ onPick, disabled }: ChatEmptyStateProps) {
  const t = useTranslations("Chat");
  return (
    <div className="flex flex-1 flex-col gap-lg overflow-y-auto px-lg py-lg">
      <div className="tp-msg-in flex flex-col items-start gap-sm">
        <div>
          <p className="text-base font-bold text-ink">{t("greetingTitle")}</p>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            {t("greetingBody")}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-sm sm:grid-cols-2">
        {CAPABILITIES.map((c, i) => (
          <button
            key={c.key}
            type="button"
            disabled={disabled}
            onClick={() => onPick(t(c.promptKey))}
            style={{ animationDelay: `${60 + i * 50}ms` }}
            className="group tp-msg-in tp-glow flex flex-col items-start gap-md rounded-[20px] bg-gradient-to-br from-lime-soft/80 via-panel to-lime-soft/25 p-lg text-left transition-all duration-200 ease-out hover:-translate-y-1 hover:[box-shadow:0_2px_4px_rgba(17,17,17,0.06),0_10px_24px_-10px_rgba(17,17,17,0.16),0_24px_56px_-14px_color-mix(in_srgb,var(--lime)_75%,transparent)] active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
          >
            <span className="flex w-full items-start justify-between">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-pill bg-panel text-ink shadow-card transition duration-200 group-hover:scale-110 group-hover:bg-lime group-hover:text-on-accent">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  {c.icon}
                </svg>
              </span>
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-pill bg-panel text-muted shadow-card transition duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:bg-ink group-hover:text-on-ink">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M7 17L17 7M9 7h8v8" />
                </svg>
              </span>
            </span>
            <span className="min-w-0">
              <span className="block text-base font-bold tracking-tight text-ink">
                {t(`capabilities.${c.key}.label`)}
              </span>
              <span className="mt-1 block text-sm leading-relaxed text-muted">
                {t(`capabilities.${c.key}.subtitle`)}
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
