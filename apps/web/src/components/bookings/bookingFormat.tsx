"use client";

import type { CSSProperties } from "react";
import { useFormatter, useTranslations } from "next-intl";

import type { Booking } from "@/lib/query/bookings";

export const iconProps = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
};

function PlaneIcon() {
    return (
        <svg {...iconProps}>
            <path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.2 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 4.3 3.5c.4.3.8.4 1.3.2l.5-.2c.4-.3.6-.7.5-1.2z" />
        </svg>
    );
}

function BedIcon() {
    return (
        <svg {...iconProps}>
            <path d="M3 18v-6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v6" />
            <path d="M3 14h18" />
            <path d="M7 10V8a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v2" />
            <path d="M3 18v2M21 18v2" />
        </svg>
    );
}

/**
 * The type marker: a line-art glyph in a tinted disc. Hotels wear the
 * hotel-blue status tone, flights the transport (amber) topic tone — the same
 * FIDS departures-board language the pills used, now scannable at a glance.
 * The disc is tinted like a Pill so it stays AA-legible and on-system.
 */
export function TypeGlyph({
    type,
    label,
    className = "size-9",
}: {
    type: Booking["type"];
    label: string;
    className?: string;
}) {
    const accent =
        type === "hotel"
            ? "var(--color-status-hotel)"
            : "var(--color-topic-transport)";
    const style: CSSProperties = {
        backgroundColor: `color-mix(in srgb, ${accent} 14%, white)`,
        color: `color-mix(in srgb, ${accent} 72%, black)`,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${accent} 24%, white)`,
    };
    return (
        <span
            style={style}
            className={`flex shrink-0 items-center justify-center rounded-pill ${className}`}
        >
            {type === "hotel" ? <BedIcon /> : <PlaneIcon />}
            <span className="sr-only">{label}</span>
        </span>
    );
}

/**
 * The API serves naive wall-clock datetimes (no offset). Pin them to UTC so we
 * render the time exactly as booked (the local departure-board time), not
 * shifted into the viewer's timezone.
 */
export function toUtcDate(iso: string): Date {
    return new Date(
        /[zZ]|[+-]\d\d:?\d\d$/.test(iso) || !iso.includes("T")
            ? iso
            : `${iso}Z`,
    );
}

/**
 * Shared booking presentation — the headline you scan for and friendly,
 * timezone-safe date formatting. Used by both the table and the detail modal
 * so the two surfaces speak the same language.
 */
export function useBookingFormat() {
    const t = useTranslations("Bookings");
    const format = useFormatter();

    const headline = (b: Booking): string =>
        b.details.kind === "flight"
            ? `${b.details.airline} · ${t("detail.routeValue", {
                  origin: b.details.origin,
                  destination: b.details.destination,
              })}`
            : b.details.hotel_name;

    // Named, timezone-safe formatters (inline literals keep next-intl's narrowed
    // option types happy). `timeZone: "UTC"` pins the naive datetimes — see
    // `toUtcDate`. Short variants for the dense table; full variants (weekday,
    // year) for the roomier detail modal.
    const day = (iso: string): string =>
        format.dateTime(toUtcDate(iso), {
            month: "short",
            day: "numeric",
            timeZone: "UTC",
        });

    const dayFull = (iso: string): string =>
        format.dateTime(toUtcDate(iso), {
            weekday: "short",
            month: "short",
            day: "numeric",
            year: "numeric",
            timeZone: "UTC",
        });

    const dateTimeShort = (iso: string): string =>
        format.dateTime(toUtcDate(iso), {
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
            timeZone: "UTC",
        });

    const dateTimeFull = (iso: string): string =>
        format.dateTime(toUtcDate(iso), {
            weekday: "short",
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
            timeZone: "UTC",
        });

    return { headline, day, dayFull, dateTimeShort, dateTimeFull };
}
