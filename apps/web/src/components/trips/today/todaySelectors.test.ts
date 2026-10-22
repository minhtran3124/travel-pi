import { describe, expect, it } from "vitest";

import type { components } from "@/lib/api/schema";

import { isWithinTrip, nextUnstarted, todayIso } from "./todaySelectors";

type TripItemStatus = components["schemas"]["TripItemStatus"];
type DayPlanItem = components["schemas"]["DayPlanItem"];

// A DayPlanItem carrying just the fields the selector reads.
function dayItem(status: TripItemStatus, sort_order: number): DayPlanItem {
  return {
    item: {
      id: `id-${sort_order}`,
      trip_id: "trip-1",
      day: 1,
      kind: "place",
      status,
      title: `item-${sort_order}`,
      sort_order,
      place_id: null,
    },
  };
}

describe("todayIso", () => {
  // Uses the browser-LOCAL calendar date, never UTC. A Date at 00:30 local on
  // 2026-06-15 in a UTC+7 zone is still 2026-06-14 in UTC — the local date must win.
  it("returns the local calendar date and never rolls back like toISOString would", () => {
    // Construct a Date whose LOCAL components are a fixed calendar day.
    const now = new Date(2026, 5, 15, 0, 30); // 15 Jun 2026, 00:30 local
    expect(todayIso(now)).toBe("2026-06-15");
    // toISOString() could disagree in a negative-offset host; the helper must not use it.
    expect(todayIso(now)).toBe(
      `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`,
    );
  });

  it("zero-pads month and day", () => {
    expect(todayIso(new Date(2026, 0, 3, 9, 0))).toBe("2026-01-03");
    expect(todayIso(new Date(2026, 11, 31, 23, 59))).toBe("2026-12-31");
  });
});

describe("isWithinTrip", () => {
  const start = "2026-06-10";
  const end = "2026-06-20";

  // Sweep every date anchor rather than pinning one "today".
  it("is false before the trip", () => {
    expect(isWithinTrip("2026-06-09", start, end)).toBe(false);
  });

  it("is true (inclusive) on the first day", () => {
    expect(isWithinTrip("2026-06-10", start, end)).toBe(true);
  });

  it("is true mid-trip", () => {
    expect(isWithinTrip("2026-06-15", start, end)).toBe(true);
  });

  it("is true (inclusive) on the last day", () => {
    expect(isWithinTrip("2026-06-20", start, end)).toBe(true);
  });

  it("is false after the trip", () => {
    expect(isWithinTrip("2026-06-21", start, end)).toBe(false);
  });

  it("returns false when startDate is null", () => {
    expect(isWithinTrip("2026-06-15", null, end)).toBe(false);
    expect(isWithinTrip("2026-06-15", undefined, end)).toBe(false);
  });

  it("treats a null endDate as open-ended: only the start bound applies", () => {
    expect(isWithinTrip("2026-06-09", start, null)).toBe(false); // before start
    expect(isWithinTrip("2026-06-10", start, null)).toBe(true); // on start
    expect(isWithinTrip("2030-01-01", start, null)).toBe(true); // far future, still within
    expect(isWithinTrip("2030-01-01", start, undefined)).toBe(true);
  });
});

describe("nextUnstarted", () => {
  it("returns null for an empty day", () => {
    expect(nextUnstarted([])).toBeNull();
  });

  it("returns null when every item is optional", () => {
    const items = [dayItem("optional", 0), dayItem("optional", 1)];
    expect(nextUnstarted(items)).toBeNull();
  });

  it("picks a pending first item with no previous", () => {
    const items = [dayItem("pending", 0), dayItem("booked", 1)];
    const result = nextUnstarted(items);
    expect(result?.previous).toBeNull();
    expect(result?.next).toBe(items[0]);
  });

  it("treats booked as unstarted", () => {
    const items = [dayItem("optional", 0), dayItem("booked", 1)];
    const result = nextUnstarted(items);
    expect(result?.previous).toBe(items[0]);
    expect(result?.next).toBe(items[1]);
  });

  it("treats a constraint as unstarted and can pick it as the first item", () => {
    const items = [dayItem("constraint", 0), dayItem("pending", 1)];
    const result = nextUnstarted(items);
    expect(result?.previous).toBeNull();
    expect(result?.next).toBe(items[0]);
  });

  it("excludes optional items and takes the first non-optional after them", () => {
    const items = [
      dayItem("optional", 0),
      dayItem("optional", 1),
      dayItem("pending", 2),
    ];
    const result = nextUnstarted(items);
    expect(result?.previous).toBe(items[1]); // the item immediately before, even though optional
    expect(result?.next).toBe(items[2]);
  });

  it("returns the previous item immediately before next in list order", () => {
    const items = [
      dayItem("pending", 0),
      dayItem("pending", 1),
      dayItem("pending", 2),
    ];
    // First unstarted is index 0, so previous is null.
    expect(nextUnstarted(items)?.next).toBe(items[0]);
    expect(nextUnstarted(items)?.previous).toBeNull();
  });
});
