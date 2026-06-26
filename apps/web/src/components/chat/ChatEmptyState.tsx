"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { AgentAvatar } from "./AgentAvatar";

export interface ChatEmptyStateProps {
  onPick: (text: string) => void;
  disabled?: boolean;
}

interface Suggestion {
  /** Translation key for the natural-language prompt sent to the agent. */
  promptKey: string;
  /** Translation key for the friendly, human chip phrasing. */
  labelKey: string;
  icon: ReactNode;
}

/**
 * First-run state for the chat. Instead of leaking internal tool names, it
 * greets the user in the well-traveled-friend voice and offers a few curated
 * starters that map to real agent capabilities (plan / find / weather / budget).
 */
const SUGGESTIONS: Suggestion[] = [
  {
    promptKey: "suggestions.planWeekendPrompt",
    labelKey: "suggestions.planWeekendLabel",
    icon: (
      <path d="M12 2l1.9 5.1L19 9l-5.1 1.9L12 16l-1.9-5.1L5 9l5.1-1.9L12 2z" />
    ),
  },
  {
    promptKey: "suggestions.findCoffeePrompt",
    labelKey: "suggestions.findCoffeeLabel",
    icon: (
      <path d="M21 10c0 6-4 11-9 11s-9-5-9-11a9 9 0 0 1 18 0zM12 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
    ),
  },
  {
    promptKey: "suggestions.checkWeatherPrompt",
    labelKey: "suggestions.checkWeatherLabel",
    icon: (
      <path d="M12 3v2m0 14v2M5.6 5.6l1.4 1.4m10 10 1.4 1.4M3 12h2m14 0h2M5.6 18.4l1.4-1.4m10-10 1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" />
    ),
  },
  {
    promptKey: "suggestions.checkBudgetPrompt",
    labelKey: "suggestions.checkBudgetLabel",
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
        <AgentAvatar size="md" />
        <div>
          <p className="text-base font-bold text-ink">{t("greetingTitle")}</p>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            {t("greetingBody")}
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-sm">
        <p className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
          {t("tryAsking")}
        </p>
        <ul className="flex flex-col gap-sm">
          {SUGGESTIONS.map((s, i) => (
            <li
              key={s.promptKey}
              className="tp-msg-in"
              style={{ animationDelay: `${60 + i * 50}ms` }}
            >
              <button
                type="button"
                disabled={disabled}
                onClick={() => onPick(t(s.promptKey))}
                className="group flex w-full items-center gap-md rounded-md border border-line bg-white px-md py-sm text-left text-sm font-medium text-ink shadow-card transition duration-150 hover:-translate-y-0.5 hover:border-[#e0e0e0] hover:shadow-lift active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 disabled:hover:shadow-card"
              >
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-sm bg-panel-raised text-muted transition-colors duration-150 group-hover:bg-lime-soft group-hover:text-ink">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    {s.icon}
                  </svg>
                </span>
                <span className="min-w-0 flex-1">{t(s.labelKey)}</span>
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  className="shrink-0 text-faint transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-ink"
                >
                  <path d="M5 12h14M13 6l6 6-6 6" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
