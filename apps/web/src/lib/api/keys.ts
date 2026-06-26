// Typed TanStack Query key factories. Each returns a readonly tuple so keys are
// stable, structurally compared, and usable as `queryKey` without widening.
export const qk = {
  trips: (filters?: Record<string, unknown>) =>
    (filters ? (["trips", filters] as const) : (["trips"] as const)),
  trip: (id: string) => ["trip", id] as const,
  items: (tripId: string) => ["items", tripId] as const,
  budget: (tripId: string) => ["budget", tripId] as const,
  expenses: (tripId: string, filters?: Record<string, unknown>) =>
    (filters
      ? (["expenses", tripId, filters] as const)
      : (["expenses", tripId] as const)),
  savedPlaces: (filters?: Record<string, unknown>) =>
    (filters ? (["savedPlaces", filters] as const) : (["savedPlaces"] as const)),
  shortlist: (tripId: string) => ["shortlist", tripId] as const,
  bookings: (filters?: Record<string, unknown>) =>
    (filters ? (["bookings", filters] as const) : (["bookings"] as const)),
  manifest: () => ["manifest"] as const,
} as const;
