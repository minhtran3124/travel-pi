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
  const parts = [
    ...(days > 0 ? [t("sections.days", { count: days })] : []),
    ...sections.map((key) => t(`sections.${key}`)),
  ];

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="research-done-card"
      className="tp-msg-in border-t border-line bg-lime-soft/40 px-lg py-md"
    >
      <div className="mb-sm flex items-start justify-between gap-sm">
        <p className="text-sm font-bold text-ink">{t("title")}</p>
        <button
          type="button"
          onClick={onDismiss}
          aria-label={t("dismiss")}
          className="shrink-0 rounded-pill px-xs text-muted transition hover:text-ink"
        >
          ×
        </button>
      </div>
      {parts.length > 0 ? (
        <p className="mb-xs text-sm leading-relaxed text-ink">
          {t("covers", { sections: parts.join(" · ") })}
        </p>
      ) : null}
      {run.proposal_ready ? (
        <p className="mb-sm text-xs text-muted">{t("proposalReady")}</p>
      ) : null}
      <Link
        href={`/trips/${encodeURIComponent(tripId)}?tab=research`}
        onClick={onDismiss}
        className="inline-block rounded-sm bg-ink px-md py-sm text-sm font-bold text-on-ink transition duration-150 hover:bg-ink-hover active:translate-y-px"
      >
        {t("open")}
      </Link>
    </div>
  );
}
