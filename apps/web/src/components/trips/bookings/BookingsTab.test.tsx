import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";

import en from "../../../../messages/en.json";
import { BookingsTab } from "./BookingsTab";

const BASE = "/api/be";
const TRIP_ID = "trip-1";

function makeBooking(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1e1f5a4-ce3a-5b24-8f2e-8a0a8b3c2c5a",
    type: "flight",
    reference_id: "FL-1",
    customer_name: "Ada Lovelace",
    customer_email: "ada@example.com",
    total_price: 420.5,
    currency: "USD",
    status: "confirmed",
    created_at: "2026-06-20T10:00:00Z",
    details: {
      kind: "flight",
      flight_id: "FL-1",
      flight_number: "VN123",
      airline: "Vietnam Airlines",
      origin: "SGN",
      destination: "HAN",
      departure_time: "2026-07-01T08:00:00Z",
      arrival_time: "2026-07-01T10:00:00Z",
      passenger_name: "Ada Lovelace",
      passenger_phone: null,
    },
    notes: null,
    confirmation_code: "ABC123",
    summary: "VN123 SGN → HAN",
    ...overrides,
  };
}

function renderTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={queryClient}>
        <BookingsTab tripId={TRIP_ID} />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

describe("BookingsTab", () => {
  it("shows an empty state with links carrying tripId when there are no bookings", async () => {
    server.use(
      http.get(`${BASE}/bookings`, ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("trip_id")).toBe(TRIP_ID);
        return HttpResponse.json({ total: 0, limit: 20, offset: 0, results: [] });
      }),
    );

    renderTab();

    await waitFor(() =>
      expect(screen.getByText("No bookings yet")).toBeInTheDocument(),
    );

    const flightLinks = screen.getAllByRole("link", { name: "Search flights" });
    const hotelLinks = screen.getAllByRole("link", { name: "Search hotels" });
    for (const link of [...flightLinks, ...hotelLinks]) {
      expect(link.getAttribute("href")).toContain(`tripId=${TRIP_ID}`);
    }
  });

  it("lists only this trip's bookings and cancels one via the detail modal", async () => {
    let cancelled = false;

    server.use(
      http.get(`${BASE}/bookings`, ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("trip_id")).toBe(TRIP_ID);
        return HttpResponse.json({
          total: 1,
          limit: 20,
          offset: 0,
          results: [
            makeBooking({ status: cancelled ? "cancelled" : "confirmed" }),
          ],
        });
      }),
      http.post(`${BASE}/bookings/:id/cancel`, () => {
        cancelled = true;
        return HttpResponse.json(makeBooking({ status: "cancelled" }));
      }),
    );

    renderTab();

    await waitFor(() =>
      expect(screen.getByText("ABC123")).toBeInTheDocument(),
    );

    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(screen.getByRole("button", { name: /ABC123/ }));

    await screen.findByRole("dialog");
    fireEvent.click(
      screen.getByRole("button", { name: "Cancel booking" }),
    );

    await waitFor(() => expect(cancelled).toBe(true));
    // A successful cancel closes the detail modal.
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("shows an error state when the request fails", async () => {
    server.use(
      http.get(`${BASE}/bookings`, () =>
        HttpResponse.json({ error: "ServerError", message: "boom" }, { status: 500 }),
      ),
    );

    renderTab();

    await waitFor(() =>
      expect(screen.getByText("Couldn't load bookings")).toBeInTheDocument(),
    );
  });
});
