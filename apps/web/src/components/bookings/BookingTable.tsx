"use client";

import { Pill } from "@/components/ui/Pill";
import type { Booking } from "@/lib/query/bookings";

export interface BookingTableProps {
  bookings: Booking[];
  onSelect: (booking: Booking) => void;
}

function TypePill({ type }: { type: Booking["type"] }) {
  // Hotels use the dedicated hotel-blue status tone; flights reuse the
  // transport (amber) topic tone — the FIDS departures-board language.
  if (type === "hotel") {
    return <Pill variant="status" tone="hotel" label="Hotel" />;
  }
  return <Pill variant="topic" tone="transport" label="Flight" />;
}

function StatusPill({ status }: { status: Booking["status"] }) {
  return status === "cancelled" ? (
    <Pill variant="status" tone="cancelled" label="Cancelled" />
  ) : (
    <Pill variant="status" tone="confirmed" label="Confirmed" />
  );
}

export function BookingTable({ bookings, onSelect }: BookingTableProps) {
  return (
    <div className="overflow-hidden rounded-md border border-line bg-panel shadow-card">
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-line text-[0.68rem] uppercase tracking-[0.08em] text-muted">
            <th className="px-md py-sm font-bold">Type</th>
            <th className="px-md py-sm font-bold">Summary</th>
            <th className="px-md py-sm font-bold">Confirmation</th>
            <th className="px-md py-sm font-bold">Status</th>
            <th className="px-md py-sm text-right font-bold">Total</th>
          </tr>
        </thead>
        <tbody>
          {bookings.map((b) => (
            <tr
              key={b.id}
              tabIndex={0}
              role="button"
              aria-label={`View booking ${b.confirmation_code}`}
              onClick={() => onSelect(b)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(b);
                }
              }}
              className="cursor-pointer border-b border-line-soft transition last:border-0 hover:bg-panel-raised"
            >
              <td className="px-md py-sm">
                <TypePill type={b.type} />
              </td>
              <td className="px-md py-sm text-ink">{b.summary}</td>
              <td className="px-md py-sm font-mono text-muted">
                {b.confirmation_code}
              </td>
              <td className="px-md py-sm">
                <StatusPill status={b.status} />
              </td>
              <td className="px-md py-sm text-right text-ink tabular-nums">
                {b.total_price.toLocaleString(undefined, {
                  style: "currency",
                  currency: b.currency,
                })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
