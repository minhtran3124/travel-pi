"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import { BookingDetailModal } from "@/components/bookings/BookingDetailModal";
import { BookingTable } from "@/components/bookings/BookingTable";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import {
  useBookings,
  useCancelBooking,
  type Booking,
} from "@/lib/query/bookings";

const linkClass =
  "inline-flex h-[34px] items-center rounded-sm border border-line bg-panel px-[18px] text-sm font-bold text-ink transition hover:bg-panel-raised active:translate-y-px";

export function BookingsTab({ tripId }: { tripId: string }) {
  const t = useTranslations("TripBookings");
  const { data, isPending, isError } = useBookings({ trip_id: tripId });
  const cancel = useCancelBooking();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const results = data?.results ?? [];
  const selected: Booking | null =
    results.find((b) => b.id === selectedId) ?? null;

  return (
    <section className="flex flex-col gap-md">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-extrabold text-ink">{t("title")}</h2>
        <div className="flex gap-sm">
          <Link href={`/flights?tripId=${tripId}`} className={linkClass}>
            {t("searchFlights")}
          </Link>
          <Link href={`/hotels?tripId=${tripId}`} className={linkClass}>
            {t("searchHotels")}
          </Link>
        </div>
      </div>

      {isPending ? (
        <Card className="flex items-center gap-sm text-sm text-muted">
          <Spinner label={t("loadingLabel")} />
          <span>{t("loading")}</span>
        </Card>
      ) : isError || !data ? (
        <Card>
          <EmptyState
            icon="⚠️"
            title={t("errorTitle")}
            hint={t("errorHint")}
          />
        </Card>
      ) : results.length === 0 ? (
        <Card>
          <EmptyState
            icon="🧳"
            title={t("emptyTitle")}
            hint={t("emptyHint")}
            action={
              <div className="flex justify-center gap-sm">
                <Link href={`/flights?tripId=${tripId}`} className={linkClass}>
                  {t("searchFlights")}
                </Link>
                <Link href={`/hotels?tripId=${tripId}`} className={linkClass}>
                  {t("searchHotels")}
                </Link>
              </div>
            }
          />
        </Card>
      ) : (
        <BookingTable bookings={results} onSelect={(b) => setSelectedId(b.id)} />
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
    </section>
  );
}
