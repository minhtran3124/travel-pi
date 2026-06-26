"use client";

import { useMemo, useState } from "react";

import { BookingDetailModal } from "@/components/bookings/BookingDetailModal";
import { BookingTable } from "@/components/bookings/BookingTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import {
  useBookings,
  useCancelBooking,
  type Booking,
} from "@/lib/query/bookings";

type TypeFilter = "all" | "flight" | "hotel";
type StatusFilter = "all" | "confirmed" | "cancelled";
type SortKey = "created_desc" | "created_asc" | "price_desc" | "price_asc";

const SELECT_CLASS =
  "h-[34px] rounded-sm border border-line bg-panel-raised px-sm text-sm text-ink";

export default function BookingsPage() {
  const { data, isLoading, isError } = useBookings();
  const cancel = useCancelBooking();

  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sort, setSort] = useState<SortKey>("created_desc");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const all = useMemo(() => data?.results ?? [], [data]);

  // Client-side search/filter/sort only — no server query params (design.md §5).
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = all.filter((b) => {
      if (typeFilter !== "all" && b.type !== typeFilter) return false;
      if (statusFilter !== "all" && b.status !== statusFilter) return false;
      if (!q) return true;
      return (
        b.id.toLowerCase().includes(q) ||
        b.confirmation_code.toLowerCase().includes(q) ||
        b.customer_name.toLowerCase().includes(q) ||
        b.customer_email.toLowerCase().includes(q) ||
        b.summary.toLowerCase().includes(q)
      );
    });

    const sorted = [...filtered].sort((a, b) => {
      switch (sort) {
        case "price_desc":
          return b.total_price - a.total_price;
        case "price_asc":
          return a.total_price - b.total_price;
        case "created_asc":
          return a.created_at.localeCompare(b.created_at);
        case "created_desc":
        default:
          return b.created_at.localeCompare(a.created_at);
      }
    });
    return sorted;
  }, [all, query, typeFilter, statusFilter, sort]);

  const selected: Booking | null =
    all.find((b) => b.id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-lg">
      <div className="flex items-baseline justify-between gap-md">
        <h1 className="text-[1.35rem] font-extrabold text-ink">Bookings</h1>
        {data ? (
          <span className="text-sm text-muted tabular-nums">
            {visible.length} of {all.length}
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-end gap-md">
        <Field
          label="Search"
          placeholder="Code, name, email…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="min-w-[14rem]"
        />
        <label className="flex flex-col gap-xs">
          <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
            Type
          </span>
          <select
            aria-label="Type"
            className={SELECT_CLASS}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as TypeFilter)}
          >
            <option value="all">All</option>
            <option value="flight">Flight</option>
            <option value="hotel">Hotel</option>
          </select>
        </label>
        <label className="flex flex-col gap-xs">
          <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
            Status
          </span>
          <select
            aria-label="Status"
            className={SELECT_CLASS}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          >
            <option value="all">All</option>
            <option value="confirmed">Confirmed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </label>
        <label className="flex flex-col gap-xs">
          <span className="text-[0.68rem] font-bold uppercase tracking-[0.08em] text-muted">
            Sort
          </span>
          <select
            aria-label="Sort"
            className={SELECT_CLASS}
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
          >
            <option value="created_desc">Newest first</option>
            <option value="created_asc">Oldest first</option>
            <option value="price_desc">Price: high to low</option>
            <option value="price_asc">Price: low to high</option>
          </select>
        </label>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-xl">
          <Spinner label="Loading bookings" />
        </div>
      ) : isError ? (
        <EmptyState
          icon="⚠️"
          title="Couldn't load bookings"
          hint="Something went wrong fetching your bookings. Try again."
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon="🧳"
          title={all.length === 0 ? "No bookings yet" : "No matching bookings"}
          hint={
            all.length === 0
              ? "Flights and hotels you book will appear here."
              : "Try adjusting your search or filters."
          }
        />
      ) : (
        <BookingTable bookings={visible} onSelect={(b) => setSelectedId(b.id)} />
      )}

      <BookingDetailModal
        booking={selected}
        open={selected !== null}
        onClose={() => setSelectedId(null)}
        onCancel={(id) =>
          cancel.mutate(id, { onSuccess: () => setSelectedId(null) })
        }
        cancelling={cancel.isPending}
      />
    </div>
  );
}
