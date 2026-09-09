// Typed TanStack Query key factories. Each returns a readonly tuple so keys are
// stable, structurally compared, and usable as `queryKey` without widening.
export const qk = {
  trips: (filters?: Record<string, unknown>) =>
    (filters ? (["trips", filters] as const) : (["trips"] as const)),
  trip: (id: string) => ["trip", id] as const,
  items: (tripId: string) => ["items", tripId] as const,
  budget: (tripId: string) => ["budget", tripId] as const,
  // `qk.expenses(tripId)` (no filters) doubles as the invalidation prefix that
  // also matches `qk.expenseSummary(tripId)` — both share `["expenses", tripId]`.
  expenses: (tripId: string, filters?: Record<string, unknown>) =>
    (filters
      ? (["expenses", tripId, filters] as const)
      : (["expenses", tripId] as const)),
  expenseSummary: (tripId: string) =>
    ["expenses", tripId, "summary"] as const,
  savedPlaces: (filters?: Record<string, unknown>) =>
    (filters ? (["savedPlaces", filters] as const) : (["savedPlaces"] as const)),
  placeSearch: (filters: Record<string, unknown>) =>
    ["placeSearch", filters] as const,
  shortlist: (tripId: string) => ["shortlist", tripId] as const,
  bookings: (filters?: Record<string, unknown>) =>
    (filters ? (["bookings", filters] as const) : (["bookings"] as const)),
  booking: (id: string) => ["booking", id] as const,
  flightSearch: (filters: Record<string, unknown>) =>
    ["flightSearch", filters] as const,
  manifest: () => ["manifest"] as const,
  visa: (city: string) => ["visa", city] as const,
  tips: (city: string) => ["tips", city] as const,
  climate: (city: string) => ["climate", city] as const,
} as const;
