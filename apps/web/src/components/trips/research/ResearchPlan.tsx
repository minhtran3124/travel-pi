"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { AssistantMarkdown } from "@/components/chat/AssistantMarkdown";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { AlreadyShortlistedError } from "@/lib/api/errors";
import { getResearchFile, type ResearchRunSummary } from "@/lib/api/research";
import { useBudget } from "@/lib/query/budget";
import { useAddItem, type TripItemCreate } from "@/lib/query/items";
import { useAddToShortlist } from "@/lib/query/shortlist";
import { FileProse } from "./FileProse";
import { FileViewer } from "./FileViewer";
import { FlightCard } from "./FlightCard";
import { HotelCard } from "./HotelCard";
import { PlaceCard } from "./PlaceCard";
import { useProposal, type Proposal } from "./proposal";

export type ApplyState = "idle" | "pending" | "ok" | "error";

/** Strip a leading slash so `/research/x.md` and `research/x.md` compare equal. */
const norm = (path: string) => path.replace(/^\/+/, "");

/** The full path in `files` whose basename matches `suffix`, or null. */
export function findFile(files: string[], suffix: string): string | null {
  return files.find((f) => norm(f).endsWith(suffix)) ?? null;
}

/** The day-N dossier files, sorted by day. */
function dayFiles(files: string[]): string[] {
  return files
    .filter((f) => /days\/day-\d+\.md$/.test(norm(f)))
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

type Translate = (key: string, values?: Record<string, string | number | Date>) => string;

/** A friendly, localized label for one report file, by basename. */
function reportLabel(path: string, t: Translate): string {
  const name = norm(path);
  const day = name.match(/days\/day-(\d+)\.md$/);
  if (day) return t("plan.report.day", { n: Number(day[1]) });
  const base = name.split("/").pop() ?? name;
  const map: Record<string, string> = {
    "summary.md": "summary",
    "overview.md": "overview",
    "flights.md": "flights",
    "stays.md": "stays",
    "entry-and-season.md": "entry",
    "budget.md": "budget",
    "proposal.json": "proposal",
  };
  const key = map[base];
  return key ? t(`plan.report.${key}`) : base;
}

/** Distinct itinerary days, ascending. */
export function itineraryDays(proposal: Proposal | undefined): number[] {
  if (!proposal) return [];
  return [...new Set(proposal.itinerary.map((e) => e.day))].sort((a, b) => a - b);
}

/**
 * Apply-to-trip state + action, shared by the Research tab plan and the chat
 * plan panel so there is one copy of the write logic. Adds each un-excluded
 * itinerary stop as a trip item and each shortlist id to the shortlist; an
 * already-shortlisted place counts as applied, not an error.
 */
export function useApplyProposal(tripId: string) {
  const addItem = useAddItem(tripId);
  const addToShortlist = useAddToShortlist(tripId);
  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  const [results, setResults] = useState<Record<string, ApplyState>>({});
  const [busy, setBusy] = useState(false);

  async function applyOne(key: string, run: () => Promise<unknown>) {
    setResults((prev) => ({ ...prev, [key]: "pending" }));
    try {
      await run();
      setResults((prev) => ({ ...prev, [key]: "ok" }));
    } catch (err) {
      const ok = err instanceof AlreadyShortlistedError;
      setResults((prev) => ({ ...prev, [key]: ok ? "ok" : "error" }));
    }
  }

  async function applyAll(proposal: Proposal) {
    setBusy(true);
    for (const [i, entry] of proposal.itinerary.entries()) {
      if (excluded.has(i)) continue;
      const body: TripItemCreate = {
        day: entry.day,
        kind: "place",
        status: "pending",
        title: entry.title,
        sort_order: 0,
        place_id: entry.place_id,
        start_time: entry.time ?? null,
        notes: entry.notes ?? null,
      };
      await applyOne(`item:${i}`, () => addItem.mutateAsync(body));
    }
    for (const [i, placeId] of proposal.shortlist.entries()) {
      await applyOne(`place:${i}`, () =>
        addToShortlist.mutateAsync({ place_id: placeId, source: "catalog" }),
      );
    }
    setBusy(false);
  }

  function toggleStop(i: number, next: boolean) {
    setExcluded((prev) => {
      const copy = new Set(prev);
      if (next) copy.delete(i);
      else copy.add(i);
      return copy;
    });
  }

  const applied = Object.values(results).filter((s) => s === "ok").length;
  const total = Object.keys(results).length;
  return { excluded, toggleStop, applyAll, busy, applied, total };
}

/**
 * The finished-run view: a plan the traveller can read and apply. Structured
 * sections come from `/plan/proposal.json` + per-id REST lookups; each section
 * degrades to the matching dossier prose when the proposal carries no ids for
 * it. The full dossier stays reachable (and editable) under a collapsed report.
 */
export function ResearchPlan({
  tripId,
  runId,
  files,
  review,
}: {
  tripId: string;
  runId: string;
  files: string[];
  review?: ResearchRunSummary["review"];
}) {
  const t = useTranslations("TripDetail.research");
  const proposalQuery = useProposal(runId, files);
  const proposal = proposalQuery.data;
  const budget = useBudget(tripId);

  const summaryPath = findFile(files, "summary.md");
  const summary = useQuery({
    queryKey: ["research", "file", runId, summaryPath ?? ""],
    enabled: summaryPath != null,
    retry: false,
    queryFn: () => getResearchFile(runId, summaryPath!),
  });

  const apply = useApplyProposal(tripId);
  const [reportOpen, setReportOpen] = useState(false);
  const [openFile, setOpenFile] = useState<string | null>(null);

  const days = itineraryDays(proposal);
  const flightIds = proposal?.flights ?? [];
  const hotelIds = proposal?.hotels ?? [];
  const dayCount = days.length > 0 ? days.length : dayFiles(files).length;

  const sortedFiles = useMemo(() => [...files].sort(), [files]);

  const flightsFile = findFile(files, "flights.md");
  const staysFile = findFile(files, "stays.md");
  const budgetFile = findFile(files, "budget.md");
  const entryFile = findFile(files, "entry-and-season.md");
  const showItinerary = days.length > 0 || dayFiles(files).length > 0;
  const showFlights = flightIds.length > 0 || flightsFile != null;
  const showStays = hotelIds.length > 0 || staysFile != null;
  const showBudget = proposal?.budgetEstimate != null || budgetFile != null;
  const showEntry = entryFile != null;

  const applyCount = proposal
    ? proposal.itinerary.filter((_, i) => !apply.excluded.has(i)).length +
      proposal.shortlist.length
    : 0;
  const needsReview = review === "needs_review";

  const stats = [
    dayCount > 0 ? t("plan.statDays", { count: dayCount }) : null,
    flightIds.length > 0 ? t("plan.statFlights", { count: flightIds.length }) : null,
    proposal?.budgetEstimate != null
      ? `$${Math.round(proposal.budgetEstimate)}`
      : null,
  ].filter(Boolean) as string[];

  return (
    <section className="flex flex-col gap-lg">
      {/* Header ------------------------------------------------------------- */}
      <Card className="flex flex-col gap-sm">
        <div className="flex items-start gap-sm">
          <span
            aria-hidden="true"
            className={
              needsReview
                ? "grid size-6 shrink-0 place-items-center rounded-pill bg-status-estimated text-on-accent text-sm font-bold"
                : "grid size-6 shrink-0 place-items-center rounded-pill bg-lime text-on-accent text-sm font-bold"
            }
          >
            {needsReview ? "!" : "✓"}
          </span>
          <h2 className="pt-[2px] text-base font-bold text-ink">
            {needsReview ? t("plan.readyTitleNeedsReview") : t("plan.readyTitle")}
          </h2>
        </div>

        {summary.data?.trim() ? (
          <div className="text-sm text-ink [&_li]:my-[0.2rem]! [&_ul]:my-0! [&_ul]:list-outside! [&_ul]:pl-[1.1rem]!">
            <AssistantMarkdown content={summary.data.trim()} isStreaming={false} />
          </div>
        ) : null}

        {needsReview ? (
          <p className="text-sm text-status-estimated">{t("plan.needsReviewHint")}</p>
        ) : null}

        {stats.length > 0 ? (
          <p className="text-xs font-medium text-muted">{stats.join(" · ")}</p>
        ) : null}

        {proposal && applyCount > 0 ? (
          <div className="flex items-center gap-sm">
            <Button onClick={() => apply.applyAll(proposal)} disabled={apply.busy}>
              {t("apply")}
            </Button>
            {apply.total > 0 && !apply.busy ? (
              <output className="text-sm font-bold text-ink">
                {t("plan.applyResult", { applied: apply.applied, total: apply.total })}
              </output>
            ) : null}
          </div>
        ) : null}
      </Card>

      {/* Section nav: jump straight to what the traveller wants to check. ---- */}
      <nav aria-label={t("plan.navLabel")}>
        <ul className="flex flex-wrap gap-xs">
          {(
            [
              [showItinerary, "research-itinerary", "plan.itineraryHeading"],
              [showFlights, "research-flights", "plan.flightsHeading"],
              [showStays, "research-stays", "plan.staysHeading"],
              [showBudget, "research-budget", "plan.budgetHeading"],
              [showEntry, "research-entry", "plan.entryHeading"],
            ] as const
          )
            .filter(([shown]) => shown)
            .map(([, anchor, label]) => (
              <li key={anchor}>
                <a
                  href={`#${anchor}`}
                  className="inline-flex rounded-pill border border-line bg-panel px-md py-xs text-sm font-medium text-ink transition hover:bg-panel-raised"
                >
                  {t(label)}
                </a>
              </li>
            ))}
        </ul>
      </nav>

      {/* Itinerary --------------------------------------------------------- */}
      {showItinerary ? (
      <PlanSection id="research-itinerary" title={t("plan.itineraryHeading")}>
        {days.length > 0 ? (
          days.map((day) => (
            <div key={day} className="flex flex-col gap-xs">
              <h4 className="text-sm font-bold text-ink">{t("plan.dayLabel", { n: day })}</h4>
              {proposal!.itinerary
                .map((entry, i) => ({ entry, i }))
                .filter(({ entry }) => entry.day === day)
                .map(({ entry, i }) => (
                  <PlaceCard
                    key={`item:${i}`}
                    entry={entry}
                    checked={!apply.excluded.has(i)}
                    onToggle={(next) => apply.toggleStop(i, next)}
                    toggleLabel={t("plan.includeStop")}
                  />
                ))}
            </div>
          ))
        ) : (
          dayFiles(files).map((path) => <FileProse key={path} runId={runId} path={path} />)
        )}
      </PlanSection>
      ) : null}

      {/* Flights ----------------------------------------------------------- */}
      {showFlights ? (
      <PlanSection id="research-flights" title={t("plan.flightsHeading")}>
        {flightIds.length > 0 ? (
          flightIds.map((id) => <FlightCard key={id} id={id} />)
        ) : (
          <SectionFallback runId={runId} path={flightsFile} />
        )}
      </PlanSection>
      ) : null}

      {/* Stays ------------------------------------------------------------- */}
      {showStays ? (
      <PlanSection id="research-stays" title={t("plan.staysHeading")}>
        {hotelIds.length > 0 ? (
          hotelIds.map((id) => <HotelCard key={id} id={id} />)
        ) : (
          <SectionFallback runId={runId} path={staysFile} />
        )}
      </PlanSection>
      ) : null}

      {/* Budget ------------------------------------------------------------ */}
      {showBudget ? (
      <PlanSection id="research-budget" title={t("plan.budgetHeading")}>
        {proposal?.budgetEstimate != null ? (
          <BudgetBar
            spent={proposal.budgetEstimate}
            cap={budget.data?.total_cap ?? null}
            lineLabel={(spent, cap) =>
              cap != null
                ? t("plan.budgetLine", { spent, cap })
                : t("plan.budgetLineNoCap", { spent })
            }
          />
        ) : (
          <SectionFallback runId={runId} path={budgetFile} />
        )}
      </PlanSection>
      ) : null}

      {/* Entry & season ---------------------------------------------------- */}
      {showEntry ? (
      <PlanSection id="research-entry" title={t("plan.entryHeading")}>
        <SectionFallback runId={runId} path={entryFile} />
      </PlanSection>
      ) : null}

      {/* Detailed report (collapsed) --------------------------------------- */}
      {sortedFiles.length > 0 ? (
        <section className="flex flex-col gap-sm">
          <button
            type="button"
            onClick={() => setReportOpen((v) => !v)}
            aria-expanded={reportOpen}
            className="flex items-center gap-xs text-sm font-bold text-muted transition hover:text-ink"
          >
            <span aria-hidden="true">{reportOpen ? "▾" : "▸"}</span>
            {t("plan.report.title")}
            <span className="font-normal">
              ({t("plan.report.count", { count: sortedFiles.length })})
            </span>
          </button>
          {reportOpen ? (
            <div className="flex flex-col gap-md md:flex-row md:items-start">
              <ul className="flex shrink-0 flex-col gap-xs md:w-[14rem]">
                {sortedFiles.map((path) => (
                  <li key={path}>
                    <button
                      type="button"
                      onClick={() => setOpenFile(path)}
                      aria-pressed={openFile === path}
                      className={
                        "w-full overflow-hidden text-ellipsis whitespace-nowrap rounded-sm border px-sm py-xs text-left text-sm transition " +
                        (openFile === path
                          ? "border-line bg-panel-raised text-ink"
                          : "border-line-soft text-muted hover:bg-panel-raised hover:text-ink")
                      }
                    >
                      {reportLabel(path, t)}
                    </button>
                  </li>
                ))}
              </ul>
              <div className="min-w-0 flex-1">
                {openFile ? <FileViewer runId={runId} path={openFile} /> : null}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

function PlanSection({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="flex scroll-mt-lg flex-col gap-sm">
      <h3 className="text-sm font-bold uppercase tracking-[0.08em] text-muted">{title}</h3>
      {children}
    </section>
  );
}

/** Section prose fallback — renders nothing when no matching file exists. */
function SectionFallback({ runId, path }: { runId: string; path: string | null }) {
  if (!path) return null;
  return <FileProse runId={runId} path={path} />;
}

export function BudgetBar({
  spent,
  cap,
  lineLabel,
}: {
  spent: number;
  cap: number | null;
  /** Render the value line; receives the rounded spent and cap (cap may be null). */
  lineLabel: (spent: number, cap: number | null) => string;
}) {
  const over = cap != null && spent > cap;
  const pct = cap && cap > 0 ? Math.min(100, Math.round((spent / cap) * 100)) : 0;
  return (
    <div className="flex flex-col gap-xs">
      {cap != null ? (
        <div className="h-2.5 w-full overflow-hidden rounded-pill bg-panel-raised">
          <div
            className={over ? "h-full bg-status-estimated" : "h-full bg-lime"}
            style={{ width: `${pct}%` }}
          />
        </div>
      ) : null}
      <p className="text-sm font-bold tabular-nums text-ink">
        {lineLabel(Math.round(spent), cap != null ? Math.round(cap) : null)}
      </p>
    </div>
  );
}
