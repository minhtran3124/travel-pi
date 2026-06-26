import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { client } from "@/lib/api/client";
import { qk } from "@/lib/api/keys";
import type { components } from "@/lib/api/schema";

export type Expense = components["schemas"]["Expense"];
export type ExpenseCreate = components["schemas"]["ExpenseCreate"];
export type ExpenseUpdate = components["schemas"]["ExpenseUpdate"];
export type ExpenseListResponse =
  components["schemas"]["ExpenseListResponse"];
export type ExpenseSummary = components["schemas"]["ExpenseSummary"];
export type ExpenseCategory = components["schemas"]["ExpenseCategory"];
export type CategoryExpense = components["schemas"]["CategoryExpense"];
export type CurrencyExpense = components["schemas"]["CurrencyExpense"];

// A type alias (not an interface) so it carries an implicit index signature and
// stays assignable to `qk.expenses`'s `Record<string, unknown>` parameter.
export type ExpenseFilters = {
  category?: ExpenseCategory;
  currency?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
};

// Prefix matching every expenses query for this trip regardless of filter
// suffix — used to invalidate the whole family after a mutation.
const expensesPrefix = (tripId: string) => ["expenses", tripId] as const;

const summaryKey = (tripId: string) =>
  ["expenses", tripId, "summary"] as const;

/** GET /trips/{id}/expenses — the ledger, newest first, optionally filtered. */
export function useExpenses(tripId: string, filters?: ExpenseFilters) {
  return useQuery({
    queryKey: filters ? qk.expenses(tripId, filters) : qk.expenses(tripId),
    queryFn: async () => {
      const { data, error } = await client.GET("/trips/{trip_id}/expenses", {
        params: { path: { trip_id: tripId }, query: filters },
      });
      if (error) throw error;
      return data;
    },
  });
}

/** GET /trips/{id}/expenses/summary — by_category / by_currency / budget actuals. */
export function useExpenseSummary(tripId: string) {
  return useQuery({
    queryKey: summaryKey(tripId),
    queryFn: async () => {
      const { data, error } = await client.GET(
        "/trips/{trip_id}/expenses/summary",
        { params: { path: { trip_id: tripId } } },
      );
      if (error) throw error;
      return data;
    },
  });
}

/** POST /trips/{id}/expenses — create a ledger entry; invalidates list + summary. */
export function useAddExpense(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ExpenseCreate) => {
      const { data, error } = await client.POST("/trips/{trip_id}/expenses", {
        params: { path: { trip_id: tripId } },
        body,
      });
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expensesPrefix(tripId) });
    },
  });
}

/** PATCH /trips/{id}/expenses/{expenseId} — partial update; invalidates list + summary. */
export function useUpdateExpense(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      body,
    }: {
      id: string;
      body: ExpenseUpdate;
    }) => {
      const { data, error } = await client.PATCH(
        "/trips/{trip_id}/expenses/{expense_id}",
        { params: { path: { trip_id: tripId, expense_id: id } }, body },
      );
      if (error) throw error;
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expensesPrefix(tripId) });
    },
  });
}

/** DELETE /trips/{id}/expenses/{expenseId} — soft delete; invalidates list + summary. */
export function useDeleteExpense(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await client.DELETE(
        "/trips/{trip_id}/expenses/{expense_id}",
        { params: { path: { trip_id: tripId, expense_id: id } } },
      );
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expensesPrefix(tripId) });
    },
  });
}
