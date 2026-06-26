"use client";

import { useFormatter, useTranslations } from "next-intl";

import {
    iconProps,
    TypeGlyph,
    useBookingFormat,
} from "@/components/bookings/bookingFormat";
import { Pill } from "@/components/ui/Pill";
import type { Booking } from "@/lib/query/bookings";

export interface BookingTableProps {
    bookings: Booking[];
    onSelect: (booking: Booking) => void;
}

function ChevronIcon() {
    return (
        <svg {...iconProps} width={16} height={16} strokeWidth={2.25}>
            <path d="m9 18 6-6-6-6" />
        </svg>
    );
}

/**
 * The headline + supporting metadata for a booking, built from the structured
 * `details` (not the server's pre-joined summary string) so the one thing you
 * scan for — the hotel name or the route — carries real weight, and dates read
 * like a travel app instead of a database dump.
 */
function useSummaryParts(b: Booking): { headline: string; meta: string } {
    const t = useTranslations("Bookings");
    const { headline, day, dateTimeShort } = useBookingFormat();
    const d = b.details;

    if (d.kind === "flight") {
        const departs = dateTimeShort(d.departure_time);
        const meta = [t("departsLabel", { date: departs }), d.passenger_name];
        return { headline: headline(b), meta: meta.join(" · ") };
    }

    const guests = d.adults + d.children;
    const meta = [
        d.city,
        `${day(d.check_in)} – ${day(d.check_out)}`,
        t("nightsCount", { count: d.nights }),
        t("roomsGuests", { rooms: d.rooms, guests }),
        b.customer_name,
    ];
    return { headline: headline(b), meta: meta.join(" · ") };
}

function BookingRow({
    booking,
    onSelect,
}: {
    booking: Booking;
    onSelect: (b: Booking) => void;
}) {
    const t = useTranslations("Bookings");
    const format = useFormatter();
    const { headline, meta } = useSummaryParts(booking);
    const isCancelled = booking.status === "cancelled";
    const typeLabel =
        booking.type === "hotel" ? t("pillHotel") : t("pillFlight");
    const total = format.number(booking.total_price, {
        style: "currency",
        currency: booking.currency,
    });

    return (
        <tr
            tabIndex={0}
            role="button"
            aria-label={t("viewBookingAria", {
                code: booking.confirmation_code,
            })}
            onClick={() => onSelect(booking)}
            onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(booking);
                }
            }}
            className="group cursor-pointer border-b border-line-soft transition-colors last:border-0 hover:bg-panel-raised focus-visible:bg-panel-raised max-sm:grid max-sm:grid-cols-[auto_1fr_auto] max-sm:items-baseline max-sm:gap-x-md max-sm:gap-y-xs max-sm:px-lg max-sm:py-md"
        >
            <td className="py-md pl-lg pr-sm align-middle max-sm:col-start-1 max-sm:row-span-2 max-sm:self-start max-sm:p-0">
                <TypeGlyph type={booking.type} label={typeLabel} />
            </td>
            <td className="py-md pr-md align-middle max-sm:col-start-2 max-sm:row-start-1 max-sm:p-0">
                <div className="font-semibold leading-tight text-ink">
                    {headline}
                </div>
                <div className="mt-0.5 text-[0.8rem] leading-snug text-muted">
                    {meta}
                </div>
            </td>
            <td className="hidden py-md pr-md align-middle sm:table-cell">
                <span className="inline-flex rounded-sm bg-panel-raised px-sm py-0.5 font-mono text-xs tracking-wide text-muted">
                    {booking.confirmation_code}
                </span>
            </td>
            <td className="py-md pr-md align-middle max-sm:col-start-2 max-sm:row-start-2 max-sm:p-0">
                <Pill
                    variant="status"
                    tone={isCancelled ? "cancelled" : "confirmed"}
                    label={
                        isCancelled ? t("pillCancelled") : t("pillConfirmed")
                    }
                />
            </td>
            <td className="py-md pl-sm pr-lg align-middle max-sm:col-start-3 max-sm:row-start-1 max-sm:self-start max-sm:p-0">
                <div className="flex items-center justify-end gap-xs">
                    <span
                        className={
                            isCancelled
                                ? "font-semibold text-faint line-through tabular-nums"
                                : "font-semibold text-ink tabular-nums"
                        }
                    >
                        {total}
                    </span>
                    <span className="text-faint opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100">
                        <ChevronIcon />
                    </span>
                </div>
            </td>
        </tr>
    );
}

export function BookingTable({ bookings, onSelect }: BookingTableProps) {
    const t = useTranslations("Bookings");
    const format = useFormatter();

    // Money-at-a-glance: sum the confirmed bookings per currency. Mixed
    // currencies stay honest (each shown), but in practice it's a single total.
    const totalsByCurrency = bookings.reduce<Record<string, number>>(
        (acc, b) => {
            if (b.status === "cancelled") return acc;
            acc[b.currency] = (acc[b.currency] ?? 0) + b.total_price;
            return acc;
        },
        {},
    );
    const confirmedTotals = Object.entries(totalsByCurrency);

    return (
        <div className="overflow-hidden rounded-md border border-line bg-panel shadow-card">
            <table className="w-full border-collapse text-left text-sm max-sm:block">
                <thead className="max-sm:hidden">
                    <tr className="border-b border-line text-[0.68rem] uppercase tracking-[0.08em] text-muted">
                        <th className="py-sm pl-lg pr-sm font-bold" scope="col">
                            <span className="sr-only">{t("tableType")}</span>
                        </th>
                        <th className="py-sm pr-md font-bold" scope="col">
                            {t("tableSummary")}
                        </th>
                        <th
                            className="hidden py-sm pr-md font-bold sm:table-cell"
                            scope="col"
                        >
                            {t("tableConfirmation")}
                        </th>
                        <th className="py-sm pr-md font-bold" scope="col">
                            {t("tableStatus")}
                        </th>
                        <th
                            className="py-sm pl-sm pr-lg text-right font-bold"
                            scope="col"
                        >
                            {t("tableTotal")}
                        </th>
                    </tr>
                </thead>
                <tbody className="max-sm:block">
                    {bookings.map((b) => (
                        <BookingRow
                            key={b.id}
                            booking={b}
                            onSelect={onSelect}
                        />
                    ))}
                </tbody>
                {confirmedTotals.length > 0 ? (
                    <tfoot className="max-sm:block">
                        <tr className="border-t border-line bg-panel-raised/40 max-sm:block">
                            <td
                                colSpan={5}
                                className="px-lg py-md max-sm:block"
                            >
                                <div className="flex items-baseline justify-between gap-md">
                                    <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
                                        {t("confirmedTotal")}
                                    </span>
                                    <span className="flex items-baseline gap-md font-bold text-ink tabular-nums">
                                        {confirmedTotals.map(
                                            ([currency, amount]) => (
                                                <span key={currency}>
                                                    {format.number(amount, {
                                                        style: "currency",
                                                        currency,
                                                    })}
                                                </span>
                                            ),
                                        )}
                                    </span>
                                </div>
                            </td>
                        </tr>
                    </tfoot>
                ) : null}
            </table>
        </div>
    );
}
