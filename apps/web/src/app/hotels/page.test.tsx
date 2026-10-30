import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

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
    renderPage();
    expect(screen.getByText("Search for a hotel")).toBeInTheDocument();
  });

  it("searches and lists results, with no booking control on the page", async () => {
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

    // Booking now happens through the chat assistant, not on this page.
    expect(
      screen.queryByRole("button", { name: "Book" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(en.Hotels.bookViaAssistantHint)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(en.Panel.simulatedData);
  });

  it("shows an error state when the search fails", async () => {
    server.use(
      http.get("/api/be/hotels/availability", () =>
        HttpResponse.json({ message: "boom" }, { status: 500 }),
      ),
    );

    renderPage();
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
      expect(screen.getByText("Couldn't search hotels")).toBeInTheDocument(),
    );
  });

  it("shows an empty state when there are no results", async () => {
    server.use(
      http.get("/api/be/hotels/availability", () =>
        HttpResponse.json({
          total: 0,
          limit: 20,
          offset: 0,
          results: [],
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
      expect(screen.getByText("No hotels found")).toBeInTheDocument(),
    );
  });
});
