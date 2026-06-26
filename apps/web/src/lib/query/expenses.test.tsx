import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw";

import { useExpenseSummary, useExpenses } from "./expenses";

const BASE = "/api/be";
const TRIP_ID = "11111111-1111-5111-8111-111111111111";

function wrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("useExpenseSummary", () => {
  it("renders by_category totals from the mocked summary response", async () => {
    server.use(
      http.get(`${BASE}/trips/:tripId/expenses/summary`, () =>
        HttpResponse.json({
          expense_count: 3,
          total_usd: 180.5,
          by_category: [
            { category: "food", total_usd: 120.25, count: 2 },
            { category: "transport", total_usd: 60.25, count: 1 },
          ],
          by_currency: [
            { currency: "USD", total_original: 180.5, total_usd: 180.5, count: 3 },
          ],
          budget: {
            total_cap: 500,
            booked_spent: 0,
            expense_spent: 180.5,
            total_spent: 180.5,
            total_remaining: 319.5,
            over_budget: false,
          },
        }),
      ),
    );

    const { result } = renderHook(() => useExpenseSummary(TRIP_ID), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.expense_count).toBe(3);
    expect(result.current.data?.by_category).toHaveLength(2);
    expect(result.current.data?.by_category[0]).toEqual({
      category: "food",
      total_usd: 120.25,
      count: 2,
    });
    expect(result.current.data?.budget.total_remaining).toBe(319.5);
  });
});

describe("useExpenses", () => {
  it("passes category/date filters as query params and parses the ledger", async () => {
    let seenUrl = "";
    server.use(
      http.get(`${BASE}/trips/:tripId/expenses`, ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json({
          total: 1,
          limit: 20,
          offset: 0,
          results: [
            {
              id: "exp-1",
              trip_id: TRIP_ID,
              category: "food",
              amount: 25,
              currency: "EUR",
              description: "Lunch",
              occurred_at: "2026-06-20T12:00:00Z",
              amount_usd: 27.5,
              fx_rate: 1.1,
              created_at: "2026-06-20T12:00:00Z",
              short_code: "EXP-ABC123",
            },
          ],
        });
      }),
    );

    const { result } = renderHook(
      () => useExpenses(TRIP_ID, { category: "food", date_from: "2026-06-01" }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.results[0].short_code).toBe("EXP-ABC123");
    expect(seenUrl).toContain("category=food");
    expect(seenUrl).toContain("date_from=2026-06-01");
  });
});
