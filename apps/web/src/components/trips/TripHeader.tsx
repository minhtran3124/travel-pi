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

function money(value: number): string {
  return value.toLocaleString("en-US", {
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
  const dayNums: number[] = [];
  const other: string[] = [];
  for (const gap of gaps) {
    const match = gap.match(/day\s+(\d+)/i);
    if (match) dayNums.push(Number(match[1]));
    else other.push(gap);
  }
  const days = [...new Set(dayNums)].sort((a, b) => a - b);
  const allOpen =
    totalDays !== null && other.length === 0 && days.length >= totalDays;

  return (
    <div className="flex flex-col gap-sm rounded-md bg-panel-raised px-md py-md">
      <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
        Still to plan
      </span>

      {allOpen ? (
        <p className="text-sm text-muted">
          Blank canvas — all {totalDays} days are open. Add your first stop in
          the <span className="font-bold text-ink">Itinerary</span> tab to start
          mapping it out.
        </p>
      ) : (
        <div className="flex flex-col gap-sm">
          {days.length > 0 ? (
            <>
              <p className="text-sm text-muted">
                <span className="font-bold text-ink">{days.length}</span>{" "}
                {days.length === 1 ? "day still needs" : "days still need"} a plan
              </p>
              <ul className="flex flex-wrap gap-xs">
                {days.map((d) => (
                  <li key={d}>
                    <span className="inline-flex rounded-pill bg-panel px-sm py-px text-xs font-bold text-muted ring-1 ring-line">
                      Day {d}
                    </span>
                  </li>
                ))}
              </ul>
            </>
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
  const range = dateRange(trip.start_date, trip.end_date);
  const status = tripStatus(trip.start_date, trip.end_date);
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
        All trips
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
            "absolute left-xl top-[132px] flex size-14 -translate-y-1/2 items-center justify-center rounded-md text-lg font-extrabold shadow-card ring-1 ring-black/5",
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
            <Stat label="Trip length" value={days === null ? "—" : `${days} ${days === 1 ? "day" : "days"}`} />
            <Stat
              label="Travelers"
              value={String(trip.travelers)}
            />
            <Stat label="Total spent" value={money(trip.total_spent)} />
            <Stat
              label="Remaining"
              value={
                trip.remaining_budget === null ||
                trip.remaining_budget === undefined
                  ? "No cap"
                  : money(trip.remaining_budget)
              }
            />
          </dl>
        </div>
      </section>

      {gaps.length > 0 ? <GapsSummary gaps={gaps} totalDays={days} /> : null}
    </header>
  );
}

/** Loading placeholder matching the hero's shape (skeleton over spinner). */
export function TripHeaderSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-lg">
      <div className="h-4 w-20 rounded-sm bg-panel-raised" />
      <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-card">
        <div className="h-[132px] animate-pulse bg-panel-raised" />
        <div className="relative px-xl pb-lg pt-[42px]">
          <div className="absolute left-xl top-[132px] size-14 -translate-y-1/2 rounded-md bg-line ring-1 ring-black/5" />
          <div className="flex flex-col gap-md">
            <div className="h-7 w-2/5 rounded-sm bg-panel-raised" />
            <div className="h-4 w-1/3 rounded-sm bg-panel-raised" />
            <div className="mt-sm grid grid-cols-2 gap-px overflow-hidden rounded-md bg-line ring-1 ring-line sm:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex flex-col gap-xs bg-panel-raised px-md py-sm">
                  <div className="h-2.5 w-12 rounded-sm bg-line" />
                  <div className="h-4 w-16 rounded-sm bg-line" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
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
