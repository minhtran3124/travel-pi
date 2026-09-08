import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

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
    renderPage();
    expect(screen.getByText("Search for a flight")).toBeInTheDocument();
  });

  it("searches and lists results, with no booking control on the page", async () => {
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

    // Booking now happens through the chat assistant, not on this page.
    expect(
      screen.queryByRole("button", { name: "Book" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(en.Flights.bookViaAssistantHint)).toBeInTheDocument();
  });

  it("shows an error state when the search fails", async () => {
    server.use(
      http.get("/api/be/flights/search", () =>
        HttpResponse.json({ message: "boom" }, { status: 500 }),
      ),
    );

    renderPage();
    fireEvent.change(screen.getByLabelText("Origin"), { target: { value: "dad" } });
    fireEvent.change(screen.getByLabelText("Destination"), {
      target: { value: "sgn" },
    });
    fireEvent.change(screen.getByLabelText("Departure date"), {
      target: { value: "2026-06-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search flights" }));

    await waitFor(() =>
      expect(screen.getByText("Couldn't search flights")).toBeInTheDocument(),
    );
  });

  it("shows an empty state when there are no results", async () => {
    server.use(
      http.get("/api/be/flights/search", () =>
        HttpResponse.json({
          count: 0,
          search: {
            origin: "DAD",
            destination: "SGN",
            departure_date: "2026-06-01",
            adults: 1,
          },
          results: [],
        }),
      ),
    );

    renderPage();
    fireEvent.change(screen.getByLabelText("Origin"), { target: { value: "dad" } });
    fireEvent.change(screen.getByLabelText("Destination"), {
      target: { value: "sgn" },
    });
    fireEvent.change(screen.getByLabelText("Departure date"), {
      target: { value: "2026-06-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search flights" }));

    await waitFor(() =>
      expect(screen.getByText("No flights found")).toBeInTheDocument(),
    );
  });
});
