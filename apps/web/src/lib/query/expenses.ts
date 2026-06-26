import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { client, unwrap } from "@/lib/api/client";
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

// `qk.expenses(tripId)` (no filters) is also the prefix matching every expenses
// query for this trip — list (with any filter suffix) AND summary — so it
// invalidates the whole family after a mutation.
const expensesPrefix = (tripId: string) => qk.expenses(tripId);

/** GET /trips/{id}/expenses — the ledger, newest first, optionally filtered. */
export function useExpenses(tripId: string, filters?: ExpenseFilters) {
  return useQuery({
    queryKey: filters ? qk.expenses(tripId, filters) : qk.expenses(tripId),
    queryFn: () =>
      unwrap(
        client.GET("/trips/{trip_id}/expenses", {
          params: { path: { trip_id: tripId }, query: filters },
        }),
      ),
  });
}

/** GET /trips/{id}/expenses/summary — by_category / by_currency / budget actuals. */
export function useExpenseSummary(tripId: string) {
  return useQuery({
    queryKey: qk.expenseSummary(tripId),
    queryFn: () =>
      unwrap(
        client.GET("/trips/{trip_id}/expenses/summary", {
          params: { path: { trip_id: tripId } },
        }),
      ),
  });
}

/** POST /trips/{id}/expenses — create a ledger entry; invalidates list + summary. */
export function useAddExpense(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ExpenseCreate) =>
      unwrap(
        client.POST("/trips/{trip_id}/expenses", {
          params: { path: { trip_id: tripId } },
          body,
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expensesPrefix(tripId) });
    },
  });
}

/** PATCH /trips/{id}/expenses/{expenseId} — partial update; invalidates list + summary. */
export function useUpdateExpense(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ExpenseUpdate }) =>
      unwrap(
        client.PATCH("/trips/{trip_id}/expenses/{expense_id}", {
          params: { path: { trip_id: tripId, expense_id: id } },
          body,
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expensesPrefix(tripId) });
    },
  });
}

/** DELETE /trips/{id}/expenses/{expenseId} — soft delete; invalidates list + summary. */
export function useDeleteExpense(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        client.DELETE("/trips/{trip_id}/expenses/{expense_id}", {
          params: { path: { trip_id: tripId, expense_id: id } },
        }),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: expensesPrefix(tripId) });
    },
  });
}
