"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";
import type { FlightsPanelData, FlightsPanelFlight } from "@/lib/stream/panel";

/**
 * Flights side-panel (specs/flights-side-panel) — a compact list so every result
 * is visible without scrolling the chat. One dense row per flight; click a row to
 * expand full detail. Read-only (no booking tool). Pure render + local expand state.
 */

function hhmm(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

function dur(mins: number): string {
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function stopLabel(stops: number): string {
  return stops === 0 ? "nonstop" : `${stops} stop${stops > 1 ? "s" : ""}`;
}

function Row({ f, cheapest }: { f: FlightsPanelFlight; cheapest: boolean }) {
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
          <div className="text-[13px] font-bold tabular-nums text-ink">
            {hhmm(f.departure_time)} → {hhmm(f.arrival_time)}{" "}
            <span className="font-medium text-faint">{dur(f.duration_minutes)}</span>
          </div>
          <div className="truncate text-[11.5px] text-muted">
            {f.airline_name} {f.flight_number} · {stopLabel(f.stops)} · {f.seats_available} left
          </div>
        </div>
        <div className="text-right">
          <div className="text-[15px] font-extrabold tabular-nums text-ink">
            ${Math.round(f.price)}
          </div>
          <div
            className="text-[10.5px] font-bold"
            style={{ color: f.stops === 0 ? "var(--color-status-confirmed)" : "var(--color-coral-ink)" }}
          >
            {stopLabel(f.stops)}
          </div>
        </div>
      </button>
      {open && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-line px-3 py-2.5 text-[12px]">
          <Detail k="Airline" v={`${f.airline_name} (${f.airline_code})`} />
          <Detail k="Flight" v={f.flight_number} />
          <Detail k="Route" v={`${f.origin} → ${f.destination}`} />
          <Detail k="Duration" v={dur(f.duration_minutes)} />
          <Detail k="Stops" v={stopLabel(f.stops)} />
          <Detail k="Seats left" v={String(f.seats_available)} />
          <Detail k="Price" v={`${f.price.toFixed(2)} ${f.currency}`} />
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

export function FlightsPanel({ data }: { data: FlightsPanelData }) {
  const { origin, destination, departure_date, results_count, cheapest_price, flights } = data;
  return (
    <div className="h-full overflow-y-auto p-md">
      <div className="mb-2.5">
        <div className="flex items-center gap-2 text-[15px] font-bold text-ink">
          {origin} <span className="font-black text-lime">→</span> {destination}
        </div>
        <div className="text-[12.5px] text-muted">
          {departure_date} · {results_count} results · cheapest ${Math.round(cheapest_price)}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        {flights.map((f) => (
          <Row key={f.id} f={f} cheapest={f.price === cheapest_price} />
        ))}
      </div>
    </div>
  );
}
