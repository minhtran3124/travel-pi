"use client";

import { useTranslations } from "next-intl";

import { toUtcDate } from "@/lib/datetime";
import { useFlightLookup } from "@/lib/query/research";

/** Wall-clock HH:MM as scheduled at the airport (naive datetimes pinned to UTC). */
function hhmm(iso: string): string {
  const d = toUtcDate(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

/**
 * One proposed flight, resolved through `GET /flights/{id}`. Skeleton while
 * loading; a failed lookup degrades to a muted line (never the raw id) so the
 * section still renders.
 */
export function FlightCard({ id }: { id: string }) {
  const t = useTranslations("TripDetail.research");
  const flight = useFlightLookup(id);

  if (flight.isPending) {
    return <div className="h-12 animate-pulse rounded-sm bg-panel-raised" />;
  }
  if (flight.isError || !flight.data) {
    return (
      <p className="rounded-sm border border-line-soft px-sm py-xs text-xs text-muted">
        {t("plan.unavailable")}
      </p>
    );
  }

  const f = flight.data;
  const stops =
    f.stops === 0 ? t("plan.nonstop") : t("plan.stops", { count: f.stops });
  return (
    <div className="flex items-center gap-sm rounded-sm border border-line-soft bg-panel px-sm py-xs">
      <span aria-hidden="true" className="text-base">
        ✈
      </span>
      <div className="min-w-0 flex-1">
        <div className="overflow-hidden text-ellipsis whitespace-nowrap text-sm font-bold text-ink">
          {f.origin} → {f.destination}{" "}
          <span className="font-medium tabular-nums text-muted">
            {hhmm(f.departure_time)}–{hhmm(f.arrival_time)}
          </span>
        </div>
        <div className="overflow-hidden text-ellipsis whitespace-nowrap text-xs text-muted">
          {f.airline.name} {f.flight_number} · {stops}
        </div>
      </div>
      <span className="shrink-0 text-sm font-extrabold tabular-nums text-ink">
        ${Math.round(f.price)}
      </span>
    </div>
  );
}
