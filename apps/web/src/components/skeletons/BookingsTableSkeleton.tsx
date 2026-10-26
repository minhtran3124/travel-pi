import { Skeleton } from "@/components/ui/Skeleton";

function BookingRowSkeleton() {
  return (
    <tr className="border-b border-line-soft last:border-0 max-sm:grid max-sm:grid-cols-[auto_1fr_auto] max-sm:items-baseline max-sm:gap-x-md max-sm:gap-y-xs max-sm:px-lg max-sm:py-md">
      <td className="py-md pl-lg pr-sm align-middle max-sm:col-start-1 max-sm:row-span-2 max-sm:self-start max-sm:p-0">
        <Skeleton className="size-6 rounded-sm" />
      </td>
      <td className="py-md pr-md align-middle max-sm:col-start-2 max-sm:row-start-1 max-sm:p-0">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-xs h-3 w-40" />
      </td>
      <td className="hidden py-md pr-md align-middle sm:table-cell">
        <Skeleton className="h-4 w-20" />
      </td>
      <td className="py-md pr-md align-middle max-sm:col-start-2 max-sm:row-start-2 max-sm:p-0">
        <Skeleton className="h-5 w-16 rounded-pill" />
      </td>
      <td className="py-md pl-sm pr-lg align-middle max-sm:col-start-3 max-sm:row-start-1 max-sm:self-start max-sm:p-0">
        <Skeleton className="ml-auto h-4 w-14" />
      </td>
    </tr>
  );
}

/**
 * `div > table > tbody` mirroring BookingTable's DOM shape, including its
 * `max-sm:block` responsive classes, so a bare `<tr>` never lands outside a
 * table in the pending branch.
 */
export function BookingsTableSkeleton() {
  return (
    <div
      data-testid="bookings-table-skeleton"
      aria-hidden="true"
      className="overflow-hidden rounded-md border border-line bg-panel shadow-card"
    >
      <table className="w-full border-collapse text-left text-sm max-sm:block">
        <tbody className="max-sm:block">
          {Array.from({ length: 6 }).map((_, i) => (
            <BookingRowSkeleton key={i} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
