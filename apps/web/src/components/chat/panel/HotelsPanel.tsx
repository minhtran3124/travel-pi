"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";
import type { HotelsPanelData, HotelsPanelHotel } from "@/lib/stream/panel";

/**
 * Hotels side-panel (specs/hotels-side-panel) — a compact list so every result is
 * visible without scrolling the chat. One dense row per hotel (name, stars,
 * nightly rate, all-in total, availability badge); click a row to expand detail
 * (short code, rating/reviews, amenities). The cheapest all-in stay is ringed in
 * lime. Read-only (no booking tool). Pure render + local expand state.
 */

function stars(n: number): string {
  return "★".repeat(n) + "☆".repeat(Math.max(0, 5 - n));
}

function Row({ h, cheapest }: { h: HotelsPanelHotel; cheapest: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div
      className={cn(
        "rounded-[11px] border border-line bg-panel shadow-card transition duration-150 hover:-translate-y-0.5 hover:border-faint hover:shadow-lift",
        cheapest && "ring-2 ring-lime",
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center gap-2.5 px-3 py-2.5 text-left active:translate-y-px"
      >
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-bold text-ink">{h.name}</div>
          <div className="truncate text-[11.5px] text-muted">
            <span className="text-amber-500">{stars(h.star_rating)}</span>{" "}
            <span className="tabular-nums">{h.rating.toFixed(1)}</span>
            {" · "}
            <span className="tabular-nums">${Math.round(h.price_per_night)}</span>/night
            {" · "}
            {h.available ? `${h.available_rooms} left` : "full"}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[15px] font-extrabold tabular-nums text-ink">
            ${Math.round(h.total_price)}
          </div>
          <div
            className="text-[10.5px] font-bold"
            style={{
              color: h.available
                ? "var(--color-status-confirmed)"
                : "var(--color-coral-ink)",
            }}
          >
            {h.available ? "available" : "full"}
          </div>
        </div>
      </button>
      {open && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-line px-3 py-2.5 text-[12px]">
          <Detail k="Short code" v={h.short_code} />
          <Detail k="Stars" v={stars(h.star_rating)} />
          <Detail k="Guest rating" v={`${h.rating.toFixed(1)} (${h.review_count} reviews)`} />
          <Detail k="Nightly rate" v={`${h.price_per_night.toFixed(2)} ${h.currency}`} />
          <Detail k="All-in total" v={`${h.total_price.toFixed(2)} ${h.currency}`} />
          <Detail k="Rooms left" v={String(h.available_rooms)} />
          <div className="col-span-2">
            <dt className="text-muted">Amenities</dt>
            <dd className="font-semibold text-ink">
              {h.amenities.length ? h.amenities.join(", ") : "—"}
            </dd>
          </div>
        </dl>
      )}
    </div>
  );
}

function Detail({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-muted">{k}</dt>
      <dd className="font-semibold text-ink">{v}</dd>
    </div>
  );
}

export function HotelsPanel({ data }: { data: HotelsPanelData }) {
  const { city, check_in, check_out, nights, rooms, results_count, cheapest_total, hotels } = data;
  return (
    <div className="h-full overflow-y-auto p-md">
      <div className="mb-2.5">
        <div className="text-[15px] font-bold text-ink">{city}</div>
        <div className="text-[12.5px] text-muted">
          {check_in} → {check_out} · {nights} night{nights === 1 ? "" : "s"} · {rooms} room
          {rooms === 1 ? "" : "s"} · {results_count} results · cheapest ${Math.round(cheapest_total)}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {hotels.map((h) => (
          <Row key={h.id} h={h} cheapest={h.total_price === cheapest_total} />
        ))}
      </div>
    </div>
  );
}
