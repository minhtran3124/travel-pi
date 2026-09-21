"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import type { ResearchRunSummary } from "@/lib/api/research";

export interface ResearchDoneCardProps {
  run: ResearchRunSummary;
  tripId: string;
  onDismiss: () => void;
}

const SECTION_FILES: ReadonlyArray<[string, string]> = [
  ["flights.md", "flights"],
  ["stays.md", "stays"],
  ["entry-and-season.md", "entry"],
  ["budget.md", "budget"],
];

/** Which dossier sections the run wrote, in reading order, from its file index. */
export function dossierSections(files: string[]): {
  sections: string[];
  days: number;
} {
  const names = new Set(files.map((f) => f.replace(/^\/+/, "")));
  return {
    sections: SECTION_FILES.filter(([file]) => names.has(file)).map(
      ([, key]) => key,
    ),
    days: [...names].filter((f) => /^days\/day-\d+\.md$/.test(f)).length,
  };
}

/**
 * Shown above the composer when a research run the chat was following
 * completes: what the dossier covers and a way into the Research tab.
 */
export function ResearchDoneCard({ run, tripId, onDismiss }: ResearchDoneCardProps) {
  const t = useTranslations("Chat.researchDone");
  const { sections, days } = dossierSections(run.files);
  const chips = [
    ...(days > 0 ? [t("sections.days", { count: days })] : []),
    ...sections.map((key) => t(`sections.${key}`)),
  ];

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="research-done-card"
      className="tp-msg-in flex gap-sm border-t border-line bg-lime-soft/40 px-lg py-md"
    >
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-pill bg-lime text-on-accent">
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

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-sm">
          <p className="pt-[2px] text-sm font-bold text-ink">{t("title")}</p>
          <button
            type="button"
            onClick={onDismiss}
            aria-label={t("dismiss")}
            className="-mr-xs shrink-0 rounded-pill px-xs text-lg leading-none text-muted transition hover:text-ink"
          >
            ×
          </button>
        </div>
        <p className="mt-xs text-sm text-muted">
          {run.proposal_ready ? t("hint") : t("hintNoPlan")}
        </p>

        {chips.length > 0 ? (
          <ul className="mt-sm flex flex-wrap gap-xs">
            {chips.map((chip) => (
              <li
                key={chip}
                className="rounded-pill border border-line bg-panel px-sm py-[2px] text-xs text-ink"
              >
                {chip}
              </li>
            ))}
          </ul>
        ) : null}

        <Link
          href={`/trips/${encodeURIComponent(tripId)}?tab=research`}
          onClick={onDismiss}
          className="mt-md inline-flex items-center gap-xs rounded-pill bg-ink px-md py-[6px] text-sm font-bold text-on-ink transition duration-150 hover:bg-ink-hover active:translate-y-px"
        >
          {t("open")}
          <span aria-hidden="true">→</span>
        </Link>
      </div>
    </div>
  );
}
