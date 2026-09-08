import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

import { server } from "@/test/msw";
import en from "../../../messages/en.json";
import FlightsPage from "./page";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={queryClient}>
        <FlightsPage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

const FLIGHT = {
  id: "flight-1",
  airline: { code: "VN", name: "Vietnam Airlines" },
  flight_number: "VN123",
  origin: "DAD",
  destination: "SGN",
  departure_time: "2026-06-01T08:00:00",
  arrival_time: "2026-06-01T09:20:00",
  duration_minutes: 80,
  price: 120,
  currency: "USD",
  seats_available: 9,
  stops: 0,
};

function mockTrips() {
  server.use(
    http.get("/api/be/trips", () =>
      HttpResponse.json({ total: 0, limit: 20, offset: 0, results: [] }),
    ),
  );
}

async function search() {
  fireEvent.change(screen.getByLabelText("Origin"), { target: { value: "dad" } });
  fireEvent.change(screen.getByLabelText("Destination"), {
    target: { value: "sgn" },
  });
  fireEvent.change(screen.getByLabelText("Departure date"), {
    target: { value: "2026-06-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search flights" }));
  await waitFor(() =>
    expect(screen.getByText(/Vietnam Airlines VN123/)).toBeInTheDocument(),
  );
}

describe("FlightsPage", () => {
  it("shows a prompt before any search", () => {
    mockTrips();
    renderPage();
    expect(screen.getByText("Search for a flight")).toBeInTheDocument();
  });

  it("searches and lists results, then opens the book dialog", async () => {
    mockTrips();
    server.use(
      http.get("/api/be/flights/search", () =>
        HttpResponse.json({
          count: 1,
          search: {
            origin: "DAD",
            destination: "SGN",
            departure_date: "2026-06-01",
            adults: 1,
          },
          results: [FLIGHT],
        }),
      ),
    );

    renderPage();
    await search();

    fireEvent.click(screen.getByRole("button", { name: "Book" }));
    expect(screen.getByRole("dialog", { name: "Book flight" })).toBeInTheDocument();
  });

  it("books a flight and shows the success state", async () => {
    mockTrips();
    server.use(
      http.get("/api/be/flights/search", () =>
        HttpResponse.json({
          count: 1,
          search: {
            origin: "DAD",
            destination: "SGN",
            departure_date: "2026-06-01",
            adults: 1,
          },
          results: [FLIGHT],
        }),
      ),
      http.post("/api/be/flights/book", () =>
        HttpResponse.json({
          id: "booking-1",
          type: "flight",
          reference_id: "flight-1",
          customer_name: "Nguyen Van A",
          customer_email: "nguyen.a@example.com",
          total_price: 120,
          currency: "USD",
          status: "confirmed",
          created_at: "2026-01-01T00:00:00Z",
          details: { kind: "flight", flight_id: "flight-1" },
          trip_id: null,
          confirmation_code: "ABC123",
          summary: "Flight DAD → SGN",
        }),
      ),
    );

    renderPage();
    await search();
    fireEvent.click(screen.getByRole("button", { name: "Book" }));

    fireEvent.change(screen.getByLabelText("Traveller name"), {
      target: { value: "Nguyen Van A" },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "nguyen.a@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Phone"), {
      target: { value: "+84 901 234 567" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm booking" }));

    await waitFor(() =>
      expect(screen.getByText("Booking confirmed")).toBeInTheDocument(),
    );
    expect(screen.getByText(/ABC123/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all bookings" })).toHaveAttribute(
      "href",
      "/bookings",
    );
  });

  it("opens the upgrade dialog on a 403", async () => {
    mockTrips();
    server.use(
      http.get("/api/be/flights/search", () =>
        HttpResponse.json({
          count: 1,
          search: {
            origin: "DAD",
            destination: "SGN",
            departure_date: "2026-06-01",
            adults: 1,
          },
          results: [FLIGHT],
        }),
      ),
      http.post("/api/be/flights/book", () =>
        HttpResponse.json(
          {
            error: "PremiumRequiredError",
            message: "Booking requires a premium plan",
            status_code: 403,
            path: "/flights/book",
            hint: "Upgrade to book flights",
          },
          { status: 403 },
        ),
      ),
    );

    renderPage();
    await search();
    fireEvent.click(screen.getByRole("button", { name: "Book" }));

    fireEvent.change(screen.getByLabelText("Traveller name"), {
      target: { value: "Nguyen Van A" },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "nguyen.a@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Phone"), {
      target: { value: "+84 901 234 567" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm booking" }));

    await waitFor(() =>
      expect(screen.getByText("Upgrade to book flights")).toBeInTheDocument(),
    );
  });
});
