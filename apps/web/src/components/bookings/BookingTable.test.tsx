import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import messages from "../../../messages/en.json";
import { BookingTable } from "./BookingTable";
import type { Booking } from "@/lib/query/bookings";

function renderTable(booking: Booking) {
    return render(
        <NextIntlClientProvider locale="en" timeZone="UTC" messages={messages}>
            <BookingTable bookings={[booking]} onSelect={() => {}} />
        </NextIntlClientProvider>,
    );
}

function makeFlightBooking(
    overrides: Partial<Booking["details"]> = {},
): Booking {
    return {
        id: "f1",
        type: "flight",
        reference_id: "fl-1",
        customer_name: "Mina Tran",
        customer_email: "mina@example.com",
        total_price: 151.83,
        currency: "USD",
        status: "confirmed",
        created_at: "2026-06-01T00:00:00Z",
        confirmation_code: "7TMS76",
        summary: "Vietnam Airlines VN123",
        details: {
            kind: "flight",
            flight_id: "fl-1",
            flight_number: "VN123",
            airline: "Vietnam Airlines",
            origin: "DAD",
            destination: "SGN",
            departure_time: "2026-10-09T06:15:00",
            arrival_time: "2026-10-09T08:00:00",
            passenger_name: "UAT Tester",
            passenger_phone: null,
            passengers: 1,
            ...overrides,
        },
    } as Booking;
}

describe("BookingTable", () => {
    it("omits the seat count for a single-seat flight booking", () => {
        renderTable(makeFlightBooking({ passengers: 1 }));

        expect(screen.getByText(/UAT Tester/)).toBeInTheDocument();
        expect(screen.queryByText(/seat/)).not.toBeInTheDocument();
    });

    it("shows the seat count for a multi-seat flight booking", () => {
        renderTable(makeFlightBooking({ passengers: 3 }));

        expect(screen.getByText(/3 seats/)).toBeInTheDocument();
    });
});
