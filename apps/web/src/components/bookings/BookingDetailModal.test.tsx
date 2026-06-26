import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import messages from "../../../messages/en.json";
import { BookingDetailModal } from "./BookingDetailModal";
import type { Booking } from "@/lib/query/bookings";

function renderModal(booking: Booking) {
    return render(
        <NextIntlClientProvider locale="en" timeZone="UTC" messages={messages}>
            <BookingDetailModal
                booking={booking}
                open
                onClose={() => {}}
                onCancel={() => {}}
            />
        </NextIntlClientProvider>,
    );
}

const flight: Booking = {
    id: "f1",
    type: "flight",
    reference_id: "fl-1",
    customer_name: "Mina Tran",
    customer_email: "mina@example.com",
    total_price: 589.22,
    currency: "USD",
    status: "confirmed",
    created_at: "2026-06-01T00:00:00Z",
    confirmation_code: "7TMS76",
    summary: "Bamboo Airways QH614",
    details: {
        kind: "flight",
        flight_id: "fl-1",
        flight_number: "QH614",
        airline: "Bamboo Airways",
        origin: "HND",
        destination: "SFO",
        // Naive wall-clock departure (no offset) — must render as 6:30, not shifted.
        departure_time: "2026-06-30T06:30:00",
        arrival_time: "2026-06-30T23:30:00",
        passenger_name: "Mina Tran",
        passenger_phone: null,
    },
} as Booking;

const hotel: Booking = {
    id: "h1",
    type: "hotel",
    reference_id: "ho-1",
    customer_name: "Mina Tran",
    customer_email: "mina@example.com",
    total_price: 1920,
    currency: "USD",
    status: "confirmed",
    created_at: "2026-06-01T00:00:00Z",
    confirmation_code: "SWJX2V",
    summary: "Hotel New Otani Tokyo",
    details: {
        kind: "hotel",
        hotel_id: "ho-1",
        hotel_name: "Hotel New Otani Tokyo",
        city: "Tokyo",
        check_in: "2026-06-24",
        check_out: "2026-06-30",
        nights: 6,
        rooms: 1,
        adults: 2,
        children: 0,
        price_per_night: 320,
        guest_phone: null,
    },
} as Booking;

describe("BookingDetailModal", () => {
    it("titles the dialog with the route headline, not the raw summary", () => {
        renderModal(flight);
        expect(
            screen.getByRole("dialog", { name: /Bamboo Airways/ }),
        ).toBeInTheDocument();
    });

    it("renders the type glyph label and confirmation code", () => {
        renderModal(flight);
        const dialog = screen.getByRole("dialog");
        // "Flight" appears in both the glyph's sr-only label and the detail row.
        expect(within(dialog).getAllByText("Flight").length).toBeGreaterThan(0);
        expect(within(dialog).getByText("7TMS76")).toBeInTheDocument();
    });

    it("formats the naive departure as a friendly local time, no tz shift, no raw ISO", () => {
        renderModal(flight);
        const dialog = screen.getByRole("dialog");
        // Jun 30 appears on both departs + arrives; 6:30 (vs the bug's 11:30 PM)
        // proves the wall-clock time survived with no timezone shift.
        expect(within(dialog).getAllByText(/Jun 30/).length).toBeGreaterThan(0);
        expect(within(dialog).getByText(/6:30/)).toBeInTheDocument();
        expect(
            within(dialog).queryByText(/2026-06-30T/),
        ).not.toBeInTheDocument();
    });

    it("formats hotel check-in as a friendly date with year", () => {
        renderModal(hotel);
        const dialog = screen.getByRole("dialog");
        expect(within(dialog).getByText(/Jun 24, 2026/)).toBeInTheDocument();
        expect(
            within(dialog).queryByText("2026-06-24"),
        ).not.toBeInTheDocument();
    });
});
