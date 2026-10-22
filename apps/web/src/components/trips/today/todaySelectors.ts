// Pure date/ordering rules for the Today tab.
//
// Every function takes its "now" as an argument — none reads the clock — so
// tests can sweep every date anchor. A single pinned "today" proves nothing
// (see docs/solutions/harness/verify-against-invented-rule.md).

import type { components } from "@/lib/api/schema";

type TripItemStatus = components["schemas"]["TripItemStatus"];
type DayPlanItem = components["schemas"]["DayPlanItem"];

/**
 * The browser-LOCAL calendar date as `YYYY-MM-DD`.
 *
 * Mirrors the local-getter mechanism of `tripVisuals.todayUTC` (which is
 * private and reads the clock, so it cannot be called with a supplied `now`):
 * read `getFullYear`/`getMonth`/`getDate`, never `toISOString`, which would be
 * UTC and roll back a day for a UTC+7 traveller before 07:00 local.
 */
export function todayIso(now: Date): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Whether `today` falls inside the trip window, inclusive at both ends.
 *
 * A null `startDate` means the trip has no start, so it can never be "in
 * progress" → `false`. A null `endDate` means the trip is open-ended, so only
 * the start bound applies. ISO `YYYY-MM-DD` strings compare lexicographically.
 */
export function isWithinTrip(
  today: string,
  startDate?: string | null,
  endDate?: string | null,
): boolean {
  if (!startDate) return false;
  if (today < startDate) return false;
  if (endDate && today > endDate) return false;
  return true;
}

const UNSTARTED: ReadonlySet<TripItemStatus> = new Set([
  "pending",
  "booked",
  "constraint",
]);

/**
 * The first unstarted item in the already-`sort_order`ed day plan, with the
 * list item immediately before it.
 *
 * "Unstarted" is `pending | booked | constraint` — `optional` is never it (a
 * decided question, not derived from `start_time`). `next` is the first such
 * item; `previous` is the item immediately before it in the list (regardless of
 * that item's own status) or `null`. Returns `null` when no unstarted item
 * exists.
 */
export function nextUnstarted(
  items: DayPlanItem[],
): { previous: DayPlanItem | null; next: DayPlanItem } | null {
  const index = items.findIndex((entry) => UNSTARTED.has(entry.item.status));
  if (index === -1) return null;
  return { previous: index > 0 ? items[index - 1] : null, next: items[index] };
}
