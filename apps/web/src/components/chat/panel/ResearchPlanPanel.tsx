"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import {
  NextIntlClientProvider,
  useLocale,
  useTranslations,
  type AbstractIntlMessages,
} from "next-intl";
import Link from "next/link";
import { useMemo, useState } from "react";

import { AssistantMarkdown } from "@/components/chat/AssistantMarkdown";
import { TripMap, type TripMapMarker } from "@/components/map/TripMap";
import { Button } from "@/components/ui/Button";
import { FlightCard } from "@/components/trips/research/FlightCard";
import { HotelCard } from "@/components/trips/research/HotelCard";
import {
  BudgetBar,
  findFile,
  itineraryDays,
  useApplyProposal,
} from "@/components/trips/research/ResearchPlan";
import {
  useProposal,
  type ProposalItinerary,
} from "@/components/trips/research/proposal";
import { getResearchFile, type ResearchRunSummary } from "@/lib/api/research";
import { useBudget } from "@/lib/query/budget";
import { placeQueryOptions } from "@/lib/query/research";
import { useTrip } from "@/lib/query/trips";
import { cn } from "@/lib/cn";

import en from "../../../../messages/en.json";
import vi from "../../../../messages/vi.json";

/**
 * The chat drawer's copy of the finished trip-research plan. Derived FE-only
 * from the trip's latest completed run (chat panels aren't persisted), so it
 * takes the run's ids and rebuilds the plan from the same REST lookups the
 * Research tab uses. Three tabs: Overview, By day (map + numbered timeline),
 * Flights & stays. Every path degrades to the summary + a link to the Research
 * tab rather than blanking.
 */
export interface ResearchPlanPanelData {
  tripId: string;
  runId: string;
  files: string[];
  review?: ResearchRunSummary["review"];
  /** A newer run is refreshing this plan: lock Apply until it settles. */
  updating?: boolean;
}

// Reused cards translate under `TripDetail.research`, so the plan panel supplies
// that namespace alongside `Panel` — the ambient PanelIntlProvider carries only
// `Panel`. Both catalogs are already imported for the panel's own copy.
const CATALOGS: Record<string, { Panel: unknown; TripDetail: unknown }> = {
  en: { Panel: en.Panel, TripDetail: en.TripDetail },
  vi: { Panel: vi.Panel, TripDetail: vi.TripDetail },
};

export function ResearchPlanPanel({ data }: { data: ResearchPlanPanelData }) {
  const locale = useLocale();
  const messages = (CATALOGS[locale] ?? CATALOGS.en) as AbstractIntlMessages;
  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <ResearchPlanBody {...data} />
    </NextIntlClientProvider>
  );
}

type Tab = "overview" | "byDay" | "flightsStays";

/** `DD–DD/MM` when one month, else `DD/MM–DD/MM`; null when no dates. */
function formatDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
): string | null {
  const part = (s: string) => {
    const [, m, d] = s.split("-").map(Number);
    return { m, d };
  };
  if (start && end) {
    const a = part(start);
    const b = part(end);
    return a.m === b.m
      ? `${a.d}–${b.d}/${a.m}`
      : `${a.d}/${a.m}–${b.d}/${b.m}`;
  }
  const only = start ?? end;
  if (!only) return null;
  const p = part(only);
  return `${p.d}/${p.m}`;
}

const CATEGORY_ICON: Record<string, string> = {
  cafe: "☕",
  restaurant: "🍜",
  attraction: "🏛️",
  activity: "🎯",
  nightlife: "🌙",
  shopping: "🛍️",
};

function ResearchPlanBody({
  tripId,
  runId,
  files,
  review,
  updating = false,
}: ResearchPlanPanelData) {
  const t = useTranslations("Panel.researchPlan");
  const trip = useTrip(tripId);
  const budget = useBudget(tripId);
  const proposal = useProposal(runId, files).data;
  const apply = useApplyProposal(tripId);

  const summaryPath = findFile(files, "summary.md");
  const summary = useQuery({
    queryKey: ["research", "file", runId, summaryPath ?? ""],
    enabled: summaryPath != null,
    retry: false,
    queryFn: () => getResearchFile(runId, summaryPath!),
  });

  const days = itineraryDays(proposal);
  const [tab, setTab] = useState<Tab>("overview");
  const [pickedDay, setPickedDay] = useState<number | null>(null);
  const activeDay = pickedDay ?? days[0] ?? null;

  const flightIds = proposal?.flights ?? [];
  const hotelIds = proposal?.hotels ?? [];
  const needsReview = review === "needs_review";

  const dateRange = formatDateRange(trip.data?.start_date, trip.data?.end_date);
  const detail = [trip.data?.city, dateRange].filter(Boolean).join(" ");
  const heading = detail ? `${t("title")} · ${detail}` : t("title");

  const stats = [
    days.length > 0 ? t("statDays", { count: days.length }) : null,
    flightIds.length > 0 ? t("statFlights", { count: flightIds.length }) : null,
    proposal?.budgetEstimate != null
      ? `$${Math.round(proposal.budgetEstimate)}`
      : null,
  ].filter(Boolean) as string[];

  const canApply =
    proposal != null &&
    (proposal.itinerary.length > 0 || proposal.shortlist.length > 0);

  const tabs: ReadonlyArray<[Tab, string]> = [
    ["overview", t("tabs.overview")],
    ["byDay", t("tabs.byDay")],
    ["flightsStays", t("tabs.flightsStays")],
  ];

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-line px-lg py-sm">
        <p className="overflow-hidden text-ellipsis whitespace-nowrap text-[15px] font-bold text-ink">
          {heading}
        </p>
      </header>

      <nav
        aria-label={t("title")}
        className="flex flex-wrap gap-xs border-b border-line px-lg py-xs"
      >
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            aria-pressed={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "rounded-full px-sm py-xs text-xs font-medium transition",
              tab === key
                ? "bg-ink text-on-ink"
                : "text-muted hover:bg-panel-raised",
            )}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="min-h-0 flex-1 overflow-y-auto p-md">
        {tab === "overview" ? (
          <div className="flex flex-col gap-md">
            <span
              className={cn(
                "inline-flex w-fit items-center gap-xs rounded-pill px-sm py-[2px] text-xs font-bold",
                needsReview
                  ? "bg-status-estimated/20 text-status-estimated"
                  : "bg-lime-soft text-ink",
              )}
            >
              <span aria-hidden="true">{needsReview ? "!" : "✓"}</span>
              {needsReview ? t("verdictNeedsReview") : t("verdictPassed")}
            </span>

            {summary.data?.trim() ? (
              <div className="text-sm text-ink [&_li]:my-[0.2rem]! [&_ul]:my-0! [&_ul]:list-outside! [&_ul]:pl-[1.1rem]!">
                <AssistantMarkdown content={summary.data.trim()} isStreaming={false} />
              </div>
            ) : null}

            {needsReview ? (
              <p className="text-sm text-status-estimated">{t("needsReviewHint")}</p>
            ) : null}

            {stats.length > 0 ? (
              <p className="text-xs font-medium text-muted">{stats.join(" · ")}</p>
            ) : null}

            {proposal?.budgetEstimate != null ? (
              <BudgetBar
                spent={proposal.budgetEstimate}
                cap={budget.data?.total_cap ?? null}
                lineLabel={(spent, cap) =>
                  cap != null
                    ? t("budgetLine", { spent, cap })
                    : t("budgetLineNoCap", { spent })
                }
              />
            ) : null}

            {canApply ? (
              <div className="flex items-center gap-sm">
                <Button
                  onClick={() => proposal && apply.applyAll(proposal)}
                  disabled={apply.busy || updating}
                >
                  {t("apply")}
                </Button>
                {updating ? (
                  <span role="status" className="text-sm font-medium text-muted">
                    {t("updating")}
                  </span>
                ) : apply.total > 0 && !apply.busy ? (
                  <output className="text-sm font-bold text-ink">
                    {t("applyResult", { applied: apply.applied, total: apply.total })}
                  </output>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {tab === "byDay" ? (
          days.length > 0 && activeDay != null ? (
            <div className="flex flex-col gap-sm">
              <div className="flex flex-wrap gap-xs">
                {days.map((d) => (
                  <button
                    key={d}
                    type="button"
                    aria-pressed={d === activeDay}
                    onClick={() => setPickedDay(d)}
                    className={cn(
                      "rounded-pill border px-sm py-[2px] text-xs font-medium transition",
                      d === activeDay
                        ? "border-line bg-ink text-on-ink"
                        : "border-line bg-panel text-muted hover:bg-panel-raised",
                    )}
                  >
                    {t("dayChip", { n: d })}
                  </button>
                ))}
              </div>
              <DayView
                entries={(proposal?.itinerary ?? []).filter((e) => e.day === activeDay)}
                mapLabel={t("mapLabel")}
              />
            </div>
          ) : (
            <p className="text-sm text-muted">{t("byDayEmpty")}</p>
          )
        ) : null}

        {tab === "flightsStays" ? (
          flightIds.length > 0 || hotelIds.length > 0 ? (
            <div className="flex flex-col gap-md">
              {flightIds.length > 0 ? (
                <section className="flex flex-col gap-xs">
                  <h3 className="text-xs font-bold uppercase tracking-[0.08em] text-muted">
                    {t("flightsHeading")}
                  </h3>
                  {flightIds.map((id) => (
                    <FlightCard key={id} id={id} />
                  ))}
                </section>
              ) : null}
              {hotelIds.length > 0 ? (
                <section className="flex flex-col gap-xs">
                  <h3 className="text-xs font-bold uppercase tracking-[0.08em] text-muted">
                    {t("staysHeading")}
                  </h3>
                  {hotelIds.map((id) => (
                    <HotelCard key={id} id={id} />
                  ))}
                </section>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted">{t("empty")}</p>
          )
        ) : null}
      </div>

      <footer className="border-t border-line px-lg py-sm">
        <Link
          href={`/trips/${encodeURIComponent(tripId)}?tab=research`}
          className="inline-flex items-center gap-xs text-sm font-bold text-ink transition hover:text-ink-hover"
        >
          {t("fullReport")}
          <span aria-hidden="true">→</span>
        </Link>
      </footer>
    </div>
  );
}

/** One stop, numbered to match its map pin. */
interface DayStop {
  entry: ProposalItinerary;
  n: number;
  name: string;
  category: string | null;
  rating: number | null;
  position: { lat: number; lng: number } | null;
}

/** Sort a day's stops by clock time; timeless stops keep their order, last. */
function byTime(entries: ProposalItinerary[]): ProposalItinerary[] {
  return [...entries].sort((a, b) => {
    if (a.time && b.time) return a.time.localeCompare(b.time);
    if (a.time) return -1;
    if (b.time) return 1;
    return 0;
  });
}

function DayView({
  entries,
  mapLabel,
}: {
  entries: ProposalItinerary[];
  mapLabel: string;
}) {
  const ordered = useMemo(() => byTime(entries), [entries]);
  const lookups = useQueries({
    queries: ordered.map((e) => placeQueryOptions(e.place_id)),
  });

  const stops: DayStop[] = useMemo(
    () =>
      ordered.map((entry, i) => {
        const place = lookups[i]?.data;
        const lat = place?.latitude;
        const lng = place?.longitude;
        return {
          entry,
          n: i + 1,
          name: place?.name ?? entry.title,
          category: place?.category ?? null,
          rating: place?.rating ?? null,
          position: lat != null && lng != null ? { lat, lng } : null,
        };
      }),
    [ordered, lookups],
  );

  // Memoized so TripMap (effect deps [markers, route]) doesn't tear down and
  // rebuild the MapLibre map on every unrelated re-render.
  const markers: TripMapMarker[] = useMemo(
    () =>
      stops
        .filter((s) => s.position != null)
        .map((s) => ({
          position: s.position!,
          label: s.name,
          badge: String(s.n),
        })),
    [stops],
  );
  const route = useMemo(
    () =>
      markers.length > 1
        ? { line: markers.map((m) => m.position), dashed: true }
        : undefined,
    [markers],
  );

  return (
    <div className="flex flex-col gap-sm">
      {markers.length > 0 ? (
        <TripMap
          markers={markers}
          route={route}
          ariaLabel={mapLabel}
          className="h-40 w-full overflow-hidden rounded-sm border border-line"
        />
      ) : null}
      <ol className="flex flex-col gap-xs">
        {stops.map((s) => (
          <li
            key={`${s.entry.place_id}:${s.n}`}
            className="flex items-center gap-sm rounded-sm border border-line-soft bg-panel px-sm py-xs"
          >
            <span
              aria-hidden="true"
              className="grid size-5 shrink-0 place-items-center rounded-pill bg-ink text-[11px] font-bold text-on-ink"
            >
              {s.n}
            </span>
            {s.entry.time ? (
              <span className="w-11 shrink-0 text-xs font-bold tabular-nums text-muted">
                {s.entry.time}
              </span>
            ) : null}
            <span aria-hidden="true" className="shrink-0 text-sm">
              {(s.category && CATEGORY_ICON[s.category]) || "📍"}
            </span>
            <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-sm font-bold text-ink">
              {s.name}
            </span>
            {s.rating != null ? (
              <span className="shrink-0 text-xs text-muted">
                <span className="text-amber-500">★</span>{" "}
                <span className="tabular-nums">{s.rating.toFixed(1)}</span>
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
