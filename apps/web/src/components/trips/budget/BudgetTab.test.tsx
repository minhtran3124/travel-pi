import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";

import en from "../../../../messages/en.json";
import { BudgetTab } from "./BudgetTab";

const BASE = "/api/be";
const TRIP_ID = "trip-1";

function makeBudget(overrides: Record<string, unknown> = {}) {
  return {
    trip_id: TRIP_ID,
    categories: {
      flights: { cap: 500, spent: 300, remaining: 200 },
      hotels: { cap: 400, spent: 350, remaining: 50 },
      activities: { cap: null, spent: 0, remaining: null },
      buffer: { cap: null, spent: 0, remaining: null },
    },
    total_cap: 900,
    total_spent: 650,
    booked_total: 800,
    total_remaining: 250,
    over_budget: false,
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
        <BudgetTab tripId={TRIP_ID} />
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}

describe("BudgetTab", () => {
  it("shows total_spent and booked_total as distinct, labeled numbers", async () => {
    server.use(
      http.get(`${BASE}/trips/:tripId/budget`, () =>
        HttpResponse.json(makeBudget()),
      ),
    );

    renderTab();

    await waitFor(() =>
      expect(screen.getByText("Total spent")).toBeInTheDocument(),
    );

    expect(screen.getByText("Booked total")).toBeInTheDocument();
    expect(
      screen.getByText(/What's counted in the itinerary/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/What's booked for this trip/),
    ).toBeInTheDocument();

    // 650 (total_spent) appears in both the category-table total row and the
    // labeled total-spent row; 800 (booked_total) is distinct and only there.
    expect(screen.getAllByText("650").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("800")).toBeInTheDocument();
  });

  it("shows an error state when the budget fails to load", async () => {
    server.use(
      http.get(`${BASE}/trips/:tripId/budget`, () =>
        HttpResponse.json({ error: "NotFound", message: "no trip" }, { status: 404 }),
      ),
    );

    renderTab();

    await waitFor(() =>
      expect(screen.getByText("Couldn't load the budget")).toBeInTheDocument(),
    );
  });
});
