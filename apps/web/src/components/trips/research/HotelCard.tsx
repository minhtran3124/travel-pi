"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { useHotelLookup } from "@/lib/query/research";

function stars(n: number): string {
  return "★".repeat(n) + "☆".repeat(Math.max(0, 5 - n));
}

/**
 * One proposed hotel, resolved through `GET /hotels/{id}`. Skeleton while
 * loading; a failed lookup degrades to a muted line (never the raw id).
 */
export function HotelCard({ id }: { id: string }) {
  const t = useTranslations("TripDetail.research");
  const hotel = useHotelLookup(id);
  const [imgError, setImgError] = useState(false);

  if (hotel.isPending) {
    return <div className="h-12 animate-pulse rounded-sm bg-panel-raised" />;
  }
  if (hotel.isError || !hotel.data) {
    return (
      <p className="rounded-sm border border-line-soft px-sm py-xs text-xs text-muted">
        {t("plan.unavailable")}
      </p>
    );
  }

  const h = hotel.data;
  return (
    <div className="flex items-center gap-sm rounded-sm border border-line-soft bg-panel px-sm py-xs">
      <div className="relative size-10 shrink-0 overflow-hidden rounded-[8px] bg-panel-raised">
        {imgError ? (
          <span className="grid h-full w-full place-items-center text-sm" aria-hidden="true">
            🏨
          </span>
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element -- external image_url across
             unconfigured domains; next/image would need remotePatterns for each. */
          <img
            src={h.image_url}
            alt={h.name}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setImgError(true)}
            className="h-full w-full object-cover"
          />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="overflow-hidden text-ellipsis whitespace-nowrap text-sm font-bold text-ink">{h.name}</div>
        <div className="overflow-hidden text-ellipsis whitespace-nowrap text-xs text-muted">
          <span className="text-amber-500">{stars(h.star_rating)}</span>{" "}
          <span className="tabular-nums">{h.rating.toFixed(1)}</span>
        </div>
      </div>
      <span className="shrink-0 text-sm font-extrabold tabular-nums text-ink">
        {t("plan.perNight", { price: `$${Math.round(h.price_per_night)}` })}
      </span>
    </div>
  );
}
