/** Placeholder matching TripCard's shape for the list loading state. */
export function TripCardSkeleton() {
  return (
    <div
      data-testid="trip-card-skeleton"
      aria-hidden="true"
      className="relative h-full animate-pulse overflow-hidden rounded-md border border-line bg-panel shadow-card"
    >
      <div className="h-[108px] bg-panel-raised" />
      <div className="absolute left-lg top-[108px] size-12 -translate-y-1/2 rounded-md bg-line ring-1 ring-line" />
      <div className="flex flex-col gap-sm px-lg pb-lg pt-[34px]">
        <div className="h-5 w-3/4 rounded-sm bg-panel-raised" />
        <div className="h-3 w-1/2 rounded-sm bg-panel-raised" />
        <div className="mt-sm flex gap-lg border-t border-line-soft pt-md">
          <div className="h-3 w-2/5 rounded-sm bg-panel-raised" />
          <div className="h-3 w-1/4 rounded-sm bg-panel-raised" />
        </div>
      </div>
    </div>
  );
}
