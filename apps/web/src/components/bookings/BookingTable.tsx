"use client";

import { useFormatter, useTranslations } from "next-intl";

import { Pill } from "@/components/ui/Pill";
import type { Booking } from "@/lib/query/bookings";

export interface BookingTableProps {
  bookings: Booking[];
  onSelect: (booking: Booking) => void;
}

function TypePill({ type }: { type: Booking["type"] }) {
  const t = useTranslations("Bookings");
  // Hotels use the dedicated hotel-blue status tone; flights reuse the
  // transport (amber) topic tone — the FIDS departures-board language.
  if (type === "hotel") {
    return <Pill variant="status" tone="hotel" label={t("pillHotel")} />;
  }
  return <Pill variant="topic" tone="transport" label={t("pillFlight")} />;
}

function StatusPill({ status }: { status: Booking["status"] }) {
  const t = useTranslations("Bookings");
  return status === "cancelled" ? (
    <Pill variant="status" tone="cancelled" label={t("pillCancelled")} />
  ) : (
    <Pill variant="status" tone="confirmed" label={t("pillConfirmed")} />
  );
}

export function BookingTable({ bookings, onSelect }: BookingTableProps) {
  const t = useTranslations("Bookings");
  const format = useFormatter();
  return (
    <div className="overflow-hidden rounded-md border border-line bg-panel shadow-card">
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-line text-[0.68rem] uppercase tracking-[0.08em] text-muted">
            <th className="px-md py-sm font-bold">{t("tableType")}</th>
            <th className="px-md py-sm font-bold">{t("tableSummary")}</th>
            <th className="px-md py-sm font-bold">{t("tableConfirmation")}</th>
            <th className="px-md py-sm font-bold">{t("tableStatus")}</th>
            <th className="px-md py-sm text-right font-bold">{t("tableTotal")}</th>
          </tr>
        </thead>
        <tbody>
          {bookings.map((b) => (
            <tr
              key={b.id}
              tabIndex={0}
              role="button"
              aria-label={t("viewBookingAria", { code: b.confirmation_code })}
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
                {format.number(b.total_price, {
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
