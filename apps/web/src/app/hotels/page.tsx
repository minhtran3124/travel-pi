"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { PanelIntlProvider } from "@/components/chat/panel/PanelIntlProvider";
import { HotelResultCard } from "@/components/hotels/HotelResultCard";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Field } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import { client, unwrap } from "@/lib/api/client";

// /hotels/search has no dates/party-size params —
// it's the date-less browse endpoint. This page needs `available`/`total_price`
// for specific dates and a party, which only /hotels/availability returns, so
// it queries that endpoint directly rather than adding a new lib/query hook
// (out of this task's declared file set).
type AvailabilityFilters = {
  city: string;
  check_in: string;
  check_out: string;
  rooms: number;
  adults: number;
  children: number;
};

function useHotelAvailability(filters: AvailabilityFilters | null) {
  return useQuery({
    queryKey: ["hotelAvailability", filters] as const,
    enabled: filters !== null,
    queryFn: () =>
      unwrap(
        client.GET("/hotels/availability", {
          params: { query: filters as AvailabilityFilters },
        }),
      ),
  });
}

export default function HotelsPage() {
  const t = useTranslations("Hotels");
  const locale = useLocale();

  const [city, setCity] = useState("");
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [rooms, setRooms] = useState("1");
  const [adults, setAdults] = useState("2");
  const [children, setChildren] = useState("0");
  const [submitted, setSubmitted] = useState<AvailabilityFilters | null>(null);

  const { data, isLoading, isError } = useHotelAvailability(submitted);
  const results = data?.results ?? [];
  const cheapestTotal = results.length
    ? Math.min(...results.map((h) => h.total_price))
    : null;

  function search(e: React.FormEvent) {
    e.preventDefault();
    if (!city.trim() || !checkIn || !checkOut) return;
    const parsedRooms = Number.parseInt(rooms, 10);
    const parsedAdults = Number.parseInt(adults, 10);
    const parsedChildren = Number.parseInt(children, 10);
    setSubmitted({
      city: city.trim(),
      check_in: checkIn,
      check_out: checkOut,
      rooms: Number.isNaN(parsedRooms) ? 1 : Math.max(1, parsedRooms),
      adults: Number.isNaN(parsedAdults) ? 1 : Math.max(1, parsedAdults),
      children: Number.isNaN(parsedChildren) ? 0 : Math.max(0, parsedChildren),
    });
  }

  return (
    <div className="flex flex-col gap-lg">
      <h1 className="text-[1.35rem] font-extrabold text-ink">{t("title")}</h1>

      <form
        onSubmit={search}
        className="flex flex-wrap items-end gap-md rounded-md border border-line bg-panel p-md"
      >
        <Field
          label={t("cityLabel")}
          placeholder={t("cityPlaceholder")}
          value={city}
          onChange={(e) => setCity(e.target.value)}
          wrapperClassName="min-w-[10rem]"
        />
        <Field
          label={t("checkInLabel")}
          type="date"
          value={checkIn}
          onChange={(e) => setCheckIn(e.target.value)}
          wrapperClassName="min-w-[10rem]"
        />
        <Field
          label={t("checkOutLabel")}
          type="date"
          value={checkOut}
          onChange={(e) => setCheckOut(e.target.value)}
          wrapperClassName="min-w-[10rem]"
        />
        <Field
          label={t("roomsLabel")}
          type="number"
          min={1}
          value={rooms}
          onChange={(e) => setRooms(e.target.value)}
          wrapperClassName="w-20"
        />
        <Field
          label={t("adultsLabel")}
          type="number"
          min={1}
          value={adults}
          onChange={(e) => setAdults(e.target.value)}
          wrapperClassName="w-20"
        />
        <Field
          label={t("childrenLabel")}
          type="number"
          min={0}
          value={children}
          onChange={(e) => setChildren(e.target.value)}
          wrapperClassName="w-20"
        />
        <Button type="submit" disabled={!city.trim() || !checkIn || !checkOut}>
          {t("searchButton")}
        </Button>
      </form>

      {submitted === null ? (
        <EmptyState icon="🏨" title={t("promptTitle")} hint={t("promptHint")} />
      ) : isLoading ? (
        <div className="flex justify-center py-xl">
          <Spinner label={t("loadingLabel")} />
        </div>
      ) : isError ? (
        <EmptyState icon="⚠️" title={t("errorTitle")} hint={t("errorHint")} />
      ) : results.length === 0 ? (
        <EmptyState icon="🏨" title={t("emptyTitle")} hint={t("emptyHint")} />
      ) : (
        <div className="flex flex-col gap-sm">
          <p className="text-sm text-muted">{t("bookViaAssistantHint")}</p>
          <PanelIntlProvider language={locale}>
            <div className="flex flex-col gap-sm">
              {results.map((h) => (
                <HotelResultCard
                  key={h.id}
                  h={h}
                  cheapest={h.total_price === cheapestTotal}
                />
              ))}
            </div>
          </PanelIntlProvider>
        </div>
      )}
    </div>
  );
}
