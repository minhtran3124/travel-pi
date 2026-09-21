"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { getResearchFile, type ResearchRunSummary } from "@/lib/api/research";
import { AssistantMarkdown } from "./AssistantMarkdown";

/** The agent's traveller-facing overview (trip_research v2, dossier-format skill). */
export const SUMMARY_FILE = "summary.md";

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

/** The run's `summary.md`, or null while loading / when the dossier has none. */
function useResearchSummary(run: ResearchRunSummary): string | null {
  const [summary, setSummary] = useState<string | null>(null);
  const hasSummary = run.files.some((f) => f.replace(/^\/+/, "") === SUMMARY_FILE);
  useEffect(() => {
    if (!hasSummary) return;
    let cancelled = false;
    const load = async () => {
      try {
        const text = await getResearchFile(run.run_id, SUMMARY_FILE);
        if (!cancelled) setSummary(text.trim() || null);
      } catch {
        // No readable summary: the card keeps its hint line.
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [run.run_id, hasSummary]);
  return summary;
}

/**
 * Shown above the composer when a research run the chat was following
 * completes: the agent's short overview, what the dossier covers, and a way
 * into the Research tab for the details.
 */
export function ResearchDoneCard({ run, tripId, onDismiss }: ResearchDoneCardProps) {
  const t = useTranslations("Chat.researchDone");
  const { sections, days } = dossierSections(run.files);
  const summary = useResearchSummary(run);
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
        {summary ? (
          // Hanging, tight bullets: Streamdown's defaults are list-inside and loose.
          <div
            data-testid="research-summary"
            className="mt-xs text-ink [&_li]:my-[0.2rem]! [&_li]:py-0! [&_li>p]:my-0! [&_ul]:ml-0! [&_ul]:list-outside! [&_ul]:pl-[1.1rem]! [&_ul]:my-0! [&_li::marker]:text-muted"
          >
            <AssistantMarkdown content={summary} isStreaming={false} />
          </div>
        ) : (
          <p className="mt-xs text-sm text-muted">
            {run.proposal_ready ? t("hint") : t("hintNoPlan")}
          </p>
        )}

        {/* The summary already walks through each section; chips only stand in for it. */}
        {!summary && chips.length > 0 ? (
          <ul data-testid="research-chips" className="mt-sm flex flex-wrap gap-xs">
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
          {summary ? t("openDetails") : t("open")}
          <span aria-hidden="true">→</span>
        </Link>
      </div>
    </div>
  );
}
