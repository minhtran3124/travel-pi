import { TripCardSkeleton } from "./TripCardSkeleton";

/** Grid of placeholder trip cards for the `/trips` loading state. */
export function TripsGridSkeleton() {
  return (
    <div
      data-testid="trips-grid-skeleton"
      aria-hidden="true"
      className="grid grid-cols-1 gap-lg sm:grid-cols-2 lg:grid-cols-3"
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <TripCardSkeleton key={i} />
      ))}
    </div>
  );
}
