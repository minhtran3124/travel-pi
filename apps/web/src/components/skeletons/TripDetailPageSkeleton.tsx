import { TripHeaderSkeleton } from "./TripHeaderSkeleton";

/** Full `/trips/[tripId]` loading placeholder: header + tab-bar shape. */
export function TripDetailPageSkeleton() {
  return (
    <div data-testid="trip-detail-page-skeleton" aria-hidden="true" className="flex flex-col gap-lg">
      <TripHeaderSkeleton />
      <div className="flex gap-md border-b border-line">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="-mb-px border-b-2 border-transparent px-xs pb-sm">
            <div className="h-4 w-16 rounded-sm bg-panel-raised" />
          </div>
        ))}
      </div>
    </div>
  );
}
