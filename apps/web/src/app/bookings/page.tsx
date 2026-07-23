"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { BookingDetailModal } from "@/components/bookings/BookingDetailModal";
import { BookingTable } from "@/components/bookings/BookingTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { Spinner } from "@/components/ui/Spinner";
import {
  useBookings,
  useCancelBooking,
  type Booking,
} from "@/lib/query/bookings";

type TypeFilter = "all" | "flight" | "hotel";
type StatusFilter = "all" | "confirmed" | "cancelled";
type SortKey = "created_desc" | "created_asc" | "price_desc" | "price_asc";

export default function BookingsPage() {
  const t = useTranslations("Bookings");
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
        <h1 className="text-[1.35rem] font-extrabold text-ink">{t("title")}</h1>
        {data ? (
          <span className="text-sm text-muted tabular-nums">
            {t("countSummary", { visible: visible.length, all: all.length })}
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-end gap-md">
        <Field
          label={t("searchLabel")}
          placeholder={t("searchPlaceholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="min-w-[14rem]"
        />
        <Select
          label={t("typeLabel")}
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as TypeFilter)}
        >
          <option value="all">{t("typeAll")}</option>
          <option value="flight">{t("typeFlight")}</option>
          <option value="hotel">{t("typeHotel")}</option>
        </Select>
        <Select
          label={t("statusLabel")}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
        >
          <option value="all">{t("statusAll")}</option>
          <option value="confirmed">{t("statusConfirmed")}</option>
          <option value="cancelled">{t("statusCancelled")}</option>
        </Select>
        <Select
          label={t("sortLabel")}
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
        >
          <option value="created_desc">{t("sortNewest")}</option>
          <option value="created_asc">{t("sortOldest")}</option>
          <option value="price_desc">{t("sortPriceDesc")}</option>
          <option value="price_asc">{t("sortPriceAsc")}</option>
        </Select>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-xl">
          <Spinner label={t("loadingLabel")} />
        </div>
      ) : isError ? (
        <EmptyState
          icon="⚠️"
          title={t("errorTitle")}
          hint={t("errorHint")}
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon="🧳"
          title={all.length === 0 ? t("emptyTitleNone") : t("emptyTitleNoMatch")}
          hint={
            all.length === 0 ? t("emptyHintNone") : t("emptyHintNoMatch")
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
