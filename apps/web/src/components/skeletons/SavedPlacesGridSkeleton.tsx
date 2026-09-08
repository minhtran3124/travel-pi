import { Skeleton } from "@/components/ui/Skeleton";

/** Placeholder matching SavedPlaceCard's shape for a single grid cell. */
function SavedPlaceCardSkeleton() {
  return (
    <div className="flex flex-col gap-sm rounded-md border border-line bg-panel p-lg shadow-card">
      <div className="flex items-start gap-sm">
        <Skeleton className="size-9 shrink-0 rounded-md" />
        <div className="min-w-0 flex-1 flex flex-col gap-xs">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-1/3" />
        </div>
      </div>
      <div className="mt-auto flex items-center gap-xs pt-sm">
        <Skeleton className="h-8 w-20" />
        <Skeleton className="h-8 w-20" />
      </div>
    </div>
  );
}

/** Grid of placeholder saved-place cards for the `/places` loading state. */
export function SavedPlacesGridSkeleton() {
  return (
    <div
      data-testid="saved-places-grid-skeleton"
      aria-hidden="true"
      className="grid grid-cols-1 gap-md sm:grid-cols-2 lg:grid-cols-3"
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <SavedPlaceCardSkeleton key={i} />
      ))}
    </div>
  );
}
