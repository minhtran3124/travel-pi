/** Loading placeholder matching the hero's shape (skeleton over spinner). */
export function TripHeaderSkeleton() {
  return (
    <div data-testid="trip-header-skeleton" aria-hidden="true" className="flex flex-col gap-lg">
      <div className="h-4 w-20 rounded-sm bg-panel-raised" />
      <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-card">
        <div className="h-[132px] animate-pulse bg-panel-raised" />
        <div className="relative px-xl pb-lg pt-[42px]">
          <div className="absolute left-xl top-[132px] size-14 -translate-y-1/2 rounded-md bg-line ring-1 ring-line" />
          <div className="flex flex-col gap-md">
            <div className="h-7 w-2/5 rounded-sm bg-panel-raised" />
            <div className="h-4 w-1/3 rounded-sm bg-panel-raised" />
            <div className="mt-sm grid grid-cols-2 gap-px overflow-hidden rounded-md bg-line ring-1 ring-line sm:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex flex-col gap-xs bg-panel-raised px-md py-sm">
                  <div className="h-2.5 w-12 rounded-sm bg-line" />
                  <div className="h-4 w-16 rounded-sm bg-line" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
