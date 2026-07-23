"use client";

import { useFormatter, useTranslations } from "next-intl";

import {
    TypeGlyph,
    useBookingFormat,
} from "@/components/bookings/bookingFormat";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Pill } from "@/components/ui/Pill";
import { Spinner } from "@/components/ui/Spinner";
import type { Booking } from "@/lib/query/bookings";

function Row({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex items-baseline justify-between gap-md py-xs">
            <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
                {label}
            </span>
            <span className="text-right text-sm text-ink">{value}</span>
        </div>
    );
}

function FlightDetails({ booking }: { booking: Booking }) {
    const t = useTranslations("Bookings");
    const { dateTimeFull } = useBookingFormat();
    const d = booking.details;
    if (d.kind !== "flight") return null;
    const at = dateTimeFull;
    return (
        <div className="flex flex-col">
            <Row
                label={t("detail.flight")}
                value={t("detail.flightValue", {
                    airline: d.airline,
                    flightNumber: d.flight_number,
                })}
            />
            <Row
                label={t("detail.route")}
                value={t("detail.routeValue", {
                    origin: d.origin,
                    destination: d.destination,
                })}
            />
            <Row label={t("detail.departs")} value={at(d.departure_time)} />
            <Row label={t("detail.arrives")} value={at(d.arrival_time)} />
            <Row label={t("detail.passenger")} value={d.passenger_name} />
            {d.passenger_phone ? (
                <Row label={t("detail.phone")} value={d.passenger_phone} />
            ) : null}
        </div>
    );
}

function HotelDetails({ booking }: { booking: Booking }) {
    const t = useTranslations("Bookings");
    const { dayFull } = useBookingFormat();
    const d = booking.details;
    if (d.kind !== "hotel") return null;
    const onDay = dayFull;
    return (
        <div className="flex flex-col">
            <Row label={t("detail.hotel")} value={d.hotel_name} />
            <Row label={t("detail.city")} value={d.city} />
            <Row label={t("detail.checkIn")} value={onDay(d.check_in)} />
            <Row label={t("detail.checkOut")} value={onDay(d.check_out)} />
            <Row label={t("detail.nights")} value={String(d.nights)} />
            <Row label={t("detail.rooms")} value={String(d.rooms)} />
            <Row
                label={t("detail.guests")}
                value={t("detail.guestsValue", {
                    adults: d.adults,
                    children: d.children,
                })}
            />
            {d.guest_phone ? (
                <Row label={t("detail.phone")} value={d.guest_phone} />
            ) : null}
        </div>
    );
}

export interface BookingDetailModalProps {
    booking: Booking | null;
    open: boolean;
    onClose: () => void;
    onCancel: (id: string) => void;
    cancelling?: boolean;
}

export function BookingDetailModal({
    booking,
    open,
    onClose,
    onCancel,
    cancelling = false,
}: BookingDetailModalProps) {
    const t = useTranslations("Bookings");
    const format = useFormatter();
    const { headline } = useBookingFormat();
    if (!booking) return null;

    const isCancelled = booking.status === "cancelled";
    const typeLabel =
        booking.type === "hotel" ? t("pillHotel") : t("pillFlight");
    const price = format.number(booking.total_price, {
        style: "currency",
        currency: booking.currency,
    });

    return (
        <Modal open={open} onClose={onClose} title={headline(booking)}>
            <div className="flex flex-col gap-md">
                <div className="flex flex-wrap items-center gap-sm">
                    <TypeGlyph
                        type={booking.type}
                        label={typeLabel}
                        className="size-8"
                    />
                    <Pill
                        variant="status"
                        tone={isCancelled ? "cancelled" : "confirmed"}
                        label={
                            isCancelled
                                ? t("pillCancelled")
                                : t("pillConfirmed")
                        }
                    />
                    <span
                        aria-label={`${t("detail.confirmation")}: ${booking.confirmation_code}`}
                        className="ml-auto inline-flex rounded-sm bg-panel-raised px-sm py-0.5 font-mono text-xs tracking-wide text-muted"
                    >
                        {booking.confirmation_code}
                    </span>
                </div>

                <div className="rounded-sm border border-line-soft bg-panel p-md">
                    {booking.details.kind === "flight" ? (
                        <FlightDetails booking={booking} />
                    ) : (
                        <HotelDetails booking={booking} />
                    )}
                </div>

                <div className="flex flex-col">
                    <Row
                        label={t("detail.customer")}
                        value={booking.customer_name}
                    />
                    <Row
                        label={t("detail.email")}
                        value={booking.customer_email}
                    />
                    <div className="flex items-baseline justify-between gap-md py-xs">
                        <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
                            {t("detail.total")}
                        </span>
                        <span className="text-right text-sm font-bold text-ink tabular-nums">
                            {price}
                        </span>
                    </div>
                </div>

                <div className="flex justify-end gap-sm">
                    <Button variant="ghost" onClick={onClose}>
                        {t("detail.close")}
                    </Button>
                    {!isCancelled ? (
                        <Button
                            variant="primary"
                            onClick={() => onCancel(booking.id)}
                            disabled={cancelling}
                        >
                            {cancelling ? (
                                <Spinner label={t("detail.cancellingLabel")} />
                            ) : (
                                t("detail.cancelBooking")
                            )}
                        </Button>
                    ) : null}
                </div>
            </div>
        </Modal>
    );
}
