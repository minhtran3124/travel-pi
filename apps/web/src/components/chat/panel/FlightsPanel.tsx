"use client";

import { useTranslations } from "next-intl";

import { FlightResultCard } from "@/components/flights/FlightResultCard";
import { SimulatedDataNote } from "@/components/ui/SimulatedDataNote";
import type { FlightsPanelData } from "@/lib/stream/panel";

/**
 * Flights side-panel (specs/flights-side-panel) — a compact list so every result
 * is visible without scrolling the chat. One dense row per flight; click a row to
 * expand full detail. Read-only (no booking tool). Pure render + local expand state.
 */

export function FlightsPanel({ data }: { data: FlightsPanelData }) {
  const t = useTranslations("Panel");
  const { origin, destination, departure_date, results_count, cheapest_price, flights } = data;
  return (
    <div className="h-full overflow-y-auto p-md">
      <div className="mb-2.5">
        <div className="flex items-center gap-2 text-[15px] font-bold text-ink">
          {origin} <span className="font-black text-lime">→</span> {destination}
        </div>
        <div className="text-[12.5px] text-muted">
          {t("flights.summary", {
            date: departure_date,
            count: results_count,
            price: `$${Math.round(cheapest_price)}`,
          })}
        </div>
      </div>
      <SimulatedDataNote className="mb-2.5" />
      <div className="flex flex-col gap-2">
        {flights.map((f, i) => (
          <div
            key={f.id}
            className="tp-row-in"
            style={{ animationDelay: `${Math.min(i, 10) * 50}ms` }}
          >
            <FlightResultCard f={f} cheapest={f.price === cheapest_price} />
          </div>
        ))}
      </div>
    </div>
  );
}
