import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";

import { cn } from "@/lib/cn";
import type { TripDetail } from "@/lib/query/trips";

import {
  CalendarIcon,
  CoverArt,
  PinIcon,
  StatusChip,
  coverForTrip,
  dateRange,
  monogram,
  tripDays,
  tripStatus,
} from "./tripVisuals";

function money(
  format: ReturnType<typeof useFormatter>,
  value: number,
): string {
  return format.number(value, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-xs bg-panel-raised px-md py-sm">
      <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
        {label}
      </span>
      <span className="text-[1.05rem] font-extrabold tabular-nums text-ink">
        {value}
      </span>
    </div>
  );
}

/**
 * The backend `gaps` list is one verbose sentence per unplanned day
 * ("Day 1 has no planned items."). Rendering all of them is a wall of noise —
 * and framing not-yet-planned days as warnings is the wrong tone. Collapse into
 * a calm nudge: a single line when the whole trip is open, compact day chips
 * when only some days are.
 */
function GapsSummary({
  gaps,
  totalDays,
}: {
  gaps: string[];
  totalDays: number | null;
}) {
  // The backend emits one gap per day, and it is *either* "no planned items"
  // (the day is empty) *or* "no accommodation booked" (the day has items but no
  // stay) — never both. Bucket them apart so a fully-planned trip that just
  // lacks a hotel reads as a calm stay nudge, not "blank canvas / needs a plan".
  const emptyDays: number[] = [];
  const stayDays: number[] = [];
  const other: string[] = [];
  for (const gap of gaps) {
    const match = gap.match(/day\s+(\d+)/i);
    const day = match ? Number(match[1]) : null;
    if (day === null) other.push(gap);
    else if (/accommodation|no stay/i.test(gap)) stayDays.push(day);
    else emptyDays.push(day);
  }
  const empties = [...new Set(emptyDays)].sort((a, b) => a - b);
  const stays = [...new Set(stayDays)].sort((a, b) => a - b);
  // "Blank canvas" only when the whole trip is genuinely empty (every day).
  const allOpen =
    totalDays !== null &&
    other.length === 0 &&
    stays.length === 0 &&
    empties.length >= totalDays;
  const t = useTranslations("TripDetail");

  return (
    <div className="flex flex-col gap-sm rounded-md bg-panel-raised px-md py-md">
      <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
        {t("gaps.stillToPlan")}
      </span>

      {allOpen ? (
        <p className="text-sm text-muted">
          {t("gaps.blankCanvas", {
            totalDays: totalDays!,
            itinerary: t("gaps.itinerary"),
          })}
        </p>
      ) : (
        <div className="flex flex-col gap-sm">
          {empties.length > 0 ? (
            <>
              <p className="text-sm text-muted">
                {t("gaps.daysNeedPlan", { count: empties.length })}
              </p>
              <ul className="flex flex-wrap gap-xs">
                {empties.map((d) => (
                  <li key={d}>
                    <span className="inline-flex rounded-pill bg-panel px-sm py-px text-xs font-bold text-muted ring-1 ring-line">
                      {t("gaps.dayChip", { day: d })}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {stays.length > 0 ? (
            <p className="text-sm text-muted">
              {t("gaps.noStay", { count: stays.length })}
            </p>
          ) : null}
          {other.length > 0 ? (
            <ul className="flex flex-col gap-xs text-sm text-muted">
              {other.map((o) => (
                <li key={o}>{o}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </div>
  );
}

export function TripHeader({ trip }: { trip: TripDetail }) {
  const t = useTranslations("TripDetail");
  const tCommon = useTranslations("Common");
  const tTrips = useTranslations("Trips");
  const format = useFormatter();
  const range = dateRange(format, tTrips, trip.start_date, trip.end_date);
  const status = tripStatus(tTrips, trip.start_date, trip.end_date);
  const now = status?.phase === "now";
  const cover = coverForTrip(trip.city || trip.title, now);
  const days = tripDays(trip.start_date, trip.end_date);
  const gaps = trip.gaps ?? [];

  return (
    <header className="flex flex-col gap-lg">
      <Link
        href="/trips"
        className="inline-flex w-fit items-center gap-xs text-sm font-bold text-muted transition hover:text-ink"
      >
        <BackArrow />
        {t("allTrips")}
      </Link>

      {/* The trip's own postcard, opened up — same deterministic cover the card
          showed, so the click-through stays continuous. `group` lets the plane
          drift on hover, echoing the card's micro-interaction. */}
      <section
        className={cn(
          "group relative overflow-hidden rounded-lg border border-line bg-panel shadow-card",
          now && "ring-2 ring-lime",
        )}
      >
        <CoverArt cover={cover} now={now} className="h-[132px]" />

        {status ? (
          <div className="absolute right-lg top-lg">
            <StatusChip status={status} />
          </div>
        ) : null}

        {/* Monogram straddles the cover seam for depth, avatar-style. */}
        <span
          aria-hidden="true"
          className={cn(
            "absolute left-xl top-[132px] flex size-14 -translate-y-1/2 items-center justify-center rounded-md text-lg font-extrabold shadow-card ring-1 ring-line",
            now ? "bg-lime text-on-accent" : "bg-panel text-ink",
          )}
        >
          {monogram(trip.city || trip.title)}
        </span>

        <div className="flex flex-col gap-lg px-xl pb-lg pt-[42px]">
          <div className="flex flex-col gap-xs">
            <h1 className="text-[1.7rem] font-extrabold leading-tight tracking-tight text-ink">
              {trip.title}
            </h1>
            <div className="flex flex-wrap items-center gap-x-md gap-y-xs text-sm text-muted">
              {trip.city ? (
                <span className="flex items-center gap-xs font-bold">
                  <PinIcon className="text-coral" />
                  {trip.city}
                </span>
              ) : null}
              {range ? (
                <span className="flex items-center gap-xs">
                  <CalendarIcon />
                  {range}
                </span>
              ) : null}
            </div>
          </div>

          {/* Hairline meta rail — gap-px over a line bg draws the 1px grid. */}
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-md bg-line ring-1 ring-line sm:grid-cols-4">
            <Stat
              label={t("stats.tripLength")}
              value={
                days === null
                  ? tCommon("notAvailable")
                  : t("tripLengthDays", { count: days })
              }
            />
            <Stat
              label={t("stats.travelers")}
              value={String(trip.travelers)}
            />
            <Stat
              label={t("stats.totalSpent")}
              value={money(format, trip.total_spent)}
            />
            <Stat
              label={t("stats.remaining")}
              value={
                trip.remaining_budget === null ||
                trip.remaining_budget === undefined
                  ? t("noCap")
                  : money(format, trip.remaining_budget)
              }
            />
          </dl>
        </div>
      </section>

      {gaps.length > 0 ? <GapsSummary gaps={gaps} totalDays={days} /> : null}
    </header>
  );
}

function BackArrow() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      <path d="M15 18l-6-6 6-6" />
    </svg>
  );
}
