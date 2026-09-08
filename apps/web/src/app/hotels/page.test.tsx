import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockSearchParams = vi.fn(() => new URLSearchParams());
vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams(),
}));

afterEach(() => {
  mockSearchParams.mockReturnValue(new URLSearchParams());
});

import { server } from "@/test/msw";
import en from "../../../messages/en.json";
import HotelsPage from "./page";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <QueryClientProvider client={queryClient}>
        <HotelsPage />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

const HOTEL = {
  id: "hotel-1",
  code: "DAD001",
  name: "Grand Da Nang Hotel",
  city: "Da Nang",
  country: "Vietnam",
  address: "1 Beach Rd",
  star_rating: 4,
  price_per_night: 100,
  currency: "USD",
  amenities: ["wifi", "pool"],
  image_url: "https://example.com/hotel.jpg",
  rating: 4.5,
  review_count: 120,
  description: "A nice hotel.",
  property_type: "Hotel",
  chain: "Independent",
  check_in_time: "14:00",
  check_out_time: "12:00",
  breakfast_included: true,
  free_cancellation: true,
  languages_spoken: ["English"],
  available: true,
  available_rooms: 5,
  max_occupancy_per_room: 2,
  nights: 2,
  total_price: 200,
  short_code: "HTL-DAD001",
};

function mockTrips() {
  server.use(
    http.get("/api/be/trips", () =>
      HttpResponse.json({ total: 0, limit: 20, offset: 0, results: [] }),
    ),
  );
}

async function search() {
  fireEvent.change(screen.getByLabelText("City"), {
    target: { value: "Da Nang" },
  });
  fireEvent.change(screen.getByLabelText("Check-in"), {
    target: { value: "2026-06-01" },
  });
  fireEvent.change(screen.getByLabelText("Check-out"), {
    target: { value: "2026-06-03" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search hotels" }));
  await waitFor(() =>
    expect(screen.getByText("Grand Da Nang Hotel")).toBeInTheDocument(),
  );
}

describe("HotelsPage", () => {
  it("shows a prompt before any search", () => {
    mockTrips();
    renderPage();
    expect(screen.getByText("Search for a hotel")).toBeInTheDocument();
  });

  it("searches and lists results, then opens the book dialog", async () => {
    mockTrips();
    server.use(
      http.get("/api/be/hotels/availability", () =>
        HttpResponse.json({
          total: 1,
          limit: 20,
          offset: 0,
          results: [HOTEL],
          search: {
            city: "Da Nang",
            check_in: "2026-06-01",
            check_out: "2026-06-03",
            nights: 2,
            rooms: 1,
            adults: 2,
            children: 0,
          },
        }),
      ),
    );

    renderPage();
    await search();

    fireEvent.click(screen.getByRole("button", { name: "Book" }));
    expect(screen.getByRole("dialog", { name: "Book hotel" })).toBeInTheDocument();
  });

  it("books a hotel and shows the success state", async () => {
    mockTrips();
    server.use(
      http.get("/api/be/hotels/availability", () =>
        HttpResponse.json({
          total: 1,
          limit: 20,
          offset: 0,
          results: [HOTEL],
          search: {
            city: "Da Nang",
            check_in: "2026-06-01",
            check_out: "2026-06-03",
            nights: 2,
            rooms: 1,
            adults: 2,
            children: 0,
          },
        }),
      ),
      http.post("/api/be/hotels/book", () =>
        HttpResponse.json({
          id: "booking-1",
          type: "hotel",
          reference_id: "hotel-1",
          customer_name: "Nguyen Van A",
          customer_email: "nguyen.a@example.com",
          total_price: 200,
          currency: "USD",
          status: "confirmed",
          created_at: "2026-01-01T00:00:00Z",
          details: { kind: "hotel", hotel_id: "hotel-1" },
          trip_id: null,
          confirmation_code: "XYZ789",
          summary: "Hotel in Da Nang",
        }),
      ),
    );

    renderPage();
    await search();
    fireEvent.click(screen.getByRole("button", { name: "Book" }));

    fireEvent.change(screen.getByLabelText("Guest name"), {
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
    expect(screen.getByText(/XYZ789/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all bookings" })).toHaveAttribute(
      "href",
      "/bookings",
    );
  });

  it("clears a prefilled ?tripId that isn't among the user's trips", async () => {
    mockSearchParams.mockReturnValue(new URLSearchParams("tripId=deleted-trip"));
    mockTrips();
    server.use(
      http.get("/api/be/hotels/availability", () =>
        HttpResponse.json({
          total: 1,
          limit: 20,
          offset: 0,
          results: [HOTEL],
          search: {
            city: "Da Nang",
            check_in: "2026-06-01",
            check_out: "2026-06-03",
            nights: 2,
            rooms: 1,
            adults: 2,
            children: 0,
          },
        }),
      ),
    );

    renderPage();
    await search();
    fireEvent.click(screen.getByRole("button", { name: "Book" }));

    // Trips load (empty — the prefilled trip has since been deleted or
    // isn't owned by this user), so the dialog's trip select must fall
    // back to "no trip" rather than silently carrying a dangling id into
    // the submit (#164).
    await waitFor(() =>
      expect(screen.getByLabelText("Trip (optional)")).toHaveValue(""),
    );
  });

  it("opens the upgrade dialog on a 403", async () => {
    mockTrips();
    server.use(
      http.get("/api/be/hotels/availability", () =>
        HttpResponse.json({
          total: 1,
          limit: 20,
          offset: 0,
          results: [HOTEL],
          search: {
            city: "Da Nang",
            check_in: "2026-06-01",
            check_out: "2026-06-03",
            nights: 2,
            rooms: 1,
            adults: 2,
            children: 0,
          },
        }),
      ),
      http.post("/api/be/hotels/book", () =>
        HttpResponse.json(
          {
            error: "PremiumRequiredError",
            message: "Booking requires a premium plan",
            status_code: 403,
            path: "/hotels/book",
            hint: "Upgrade to book hotels",
          },
          { status: 403 },
        ),
      ),
    );

    renderPage();
    await search();
    fireEvent.click(screen.getByRole("button", { name: "Book" }));

    fireEvent.change(screen.getByLabelText("Guest name"), {
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
      expect(screen.getByText("Upgrade to book hotels")).toBeInTheDocument(),
    );
  });
});
