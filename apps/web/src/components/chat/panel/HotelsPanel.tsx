"use client";

import { useTranslations } from "next-intl";

import { HotelResultCard } from "@/components/hotels/HotelResultCard";
import { SimulatedDataNote } from "@/components/ui/SimulatedDataNote";
import type { HotelsPanelData } from "@/lib/stream/panel";

/**
 * Hotels side-panel (specs/hotels-side-panel) — a compact list so every result is
 * visible without scrolling the chat. One row per hotel: a thumbnail, name, stars,
 * guest rating, nightly rate, all-in total, and an availability badge; click a row
 * to expand detail (description, rating/reviews, amenities). The cheapest all-in stay is
 * ringed in lime. Read-only (no booking tool). Pure render + local expand state.
 */

export function HotelsPanel({ data }: { data: HotelsPanelData }) {
  const t = useTranslations("Panel");
  const { city, check_in, check_out, nights, rooms, results_count, cheapest_total, hotels } = data;
  return (
    <div className="h-full overflow-y-auto p-md">
      <div className="mb-2.5">
        <div className="text-[15px] font-bold text-ink">{city}</div>
        <div className="text-[12.5px] text-muted">
          {t("hotels.summary", {
            checkIn: check_in,
            checkOut: check_out,
            nights,
            rooms,
            results: results_count,
            price: `$${Math.round(cheapest_total)}`,
          })}
        </div>
      </div>
      <SimulatedDataNote className="mb-2.5" />
      <div className="flex flex-col gap-2">
        {hotels.map((h, i) => (
          <div
            key={h.id}
            className="tp-row-in"
            style={{ animationDelay: `${Math.min(i, 10) * 50}ms` }}
          >
            <HotelResultCard h={h} cheapest={h.total_price === cheapest_total} />
          </div>
        ))}
      </div>
    </div>
  );
}

