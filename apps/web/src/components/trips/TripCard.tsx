import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";

import { cn } from "@/lib/cn";
import type { Trip } from "@/lib/query/trips";

import {
  CalendarIcon,
  CoverArt,
  PinIcon,
  StatusChip,
  UsersIcon,
  coverForTrip,
  dateRange,
  monogram,
  tripStatus,
} from "./tripVisuals";

export function TripCard({ trip }: { trip: Trip }) {
  const t = useTranslations("Trips");
  const format = useFormatter();
  const range = dateRange(format, t, trip.start_date, trip.end_date);
  const status = tripStatus(t, trip.start_date, trip.end_date);
  const now = status?.phase === "now";
  const cover = coverForTrip(trip.city || trip.title, now);

  return (
    <Link href={`/trips/${trip.id}`} className="group block">
      <article
        className={cn(
          "relative flex h-full flex-col overflow-hidden rounded-md border border-line bg-panel shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-[#e0e0e0] hover:shadow-lift",
          now && "ring-2 ring-lime",
        )}
      >
        <CoverArt cover={cover} now={now} />

        {status ? (
          <div className="absolute right-md top-md">
            <StatusChip status={status} />
          </div>
        ) : null}

        {/* Monogram straddles the cover seam for depth, avatar-style. */}
        <span
          aria-hidden="true"
          className={cn(
            "absolute left-lg top-[108px] flex size-12 -translate-y-1/2 items-center justify-center rounded-md text-base font-extrabold shadow-card ring-1 ring-black/5",
            now ? "bg-lime text-on-accent" : "bg-panel text-ink",
          )}
        >
          {monogram(trip.city || trip.title)}
        </span>

        <div className="flex flex-1 flex-col gap-xs px-lg pb-lg pt-[34px]">
          <h3 className="line-clamp-2 break-words text-[1.2rem] font-extrabold leading-tight text-ink">
            {trip.title}
          </h3>

          {trip.city ? (
            <p className="flex items-center gap-xs text-sm font-bold text-muted">
              <PinIcon className="text-coral" />
              {trip.city}
            </p>
          ) : null}

          <div className="mt-auto flex flex-wrap items-center gap-x-lg gap-y-xs border-t border-line-soft pt-md text-sm text-muted">
            <span className="flex items-center gap-xs">
              <CalendarIcon />
              {range ?? t("card.noDatesYet")}
            </span>
            <span className="flex items-center gap-xs">
              <UsersIcon />
              {t("card.travelers", { count: trip.travelers })}
            </span>
          </div>
        </div>
      </article>
    </Link>
  );
}

/** Placeholder matching {@link TripCard}'s shape for the list loading state. */
export function TripCardSkeleton() {
  return (
    <div
      aria-hidden="true"
      className="relative h-full animate-pulse overflow-hidden rounded-md border border-line bg-panel shadow-card"
    >
      <div className="h-[108px] bg-panel-raised" />
      <div className="absolute left-lg top-[108px] size-12 -translate-y-1/2 rounded-md bg-line ring-1 ring-black/5" />
      <div className="flex flex-col gap-sm px-lg pb-lg pt-[34px]">
        <div className="h-5 w-3/4 rounded-sm bg-panel-raised" />
        <div className="h-3 w-1/2 rounded-sm bg-panel-raised" />
        <div className="mt-sm flex gap-lg border-t border-line-soft pt-md">
          <div className="h-3 w-2/5 rounded-sm bg-panel-raised" />
          <div className="h-3 w-1/4 rounded-sm bg-panel-raised" />
        </div>
      </div>
    </div>
  );
}
